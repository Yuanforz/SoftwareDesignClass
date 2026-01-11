import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from loguru import logger

from ..agent.output_types import DisplayText, Actions
from ..live2d_model import Live2dModel
from ..tts.tts_interface import TTSInterface
from ..utils.stream_audio import prepare_audio_payload, get_audio_duration
from ..config_manager.utils import get_lingxi_settings
from .types import WebSocketSend


class TTSTaskManager:
    """Manages TTS tasks and ensures ordered delivery to frontend while allowing parallel TTS generation"""

    def __init__(self) -> None:
        self.task_list: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        # Queue to store ordered payloads
        self._payload_queue: asyncio.Queue[Dict] = asyncio.Queue()
        # Task to handle sending payloads in order
        self._sender_task: Optional[asyncio.Task] = None
        # Counter for maintaining order
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        
        # 音频合并缓冲区（仅用于 Step TTS）
        # 存储元组: (tts_text, display_text, actions)
        # 注意：只有通过标题过滤的有效 TTS 文本才会进入缓冲区
        self._merge_buffer: List[Tuple[str, DisplayText, Optional[Actions]]] = []
        self._merge_max_sentences = 3
        
        # 渐进式合并相关
        # 用于追踪当前对话的句子数，实现 1->2->3 渐进式缓冲
        self._progressive_sentence_count = 0
        self._progressive_merge_enabled = True
        # 当前轮次的有效缓冲大小（在新一轮开始时锁定）
        self._current_round_max = 1

    def _is_title_content(self, text: str) -> bool:
        """
        检查文本是否是标题内容（以 # 开头）。
        """
        return text.strip().startswith('#')

    def _is_emotion_tag_only(self, text: str) -> bool:
        """
        检查文本是否仅包含情感标签（如 [neutral], [joy] 等）。
        这些标签不应该被朗读。
        """
        # 移除所有方括号标签后检查是否为空
        cleaned = re.sub(r'\[\w+\]', '', text).strip()
        return len(cleaned) == 0 and '[' in text

    def _remove_emotion_tags(self, text: str) -> str:
        """
        移除文本中的情感标签。
        """
        return re.sub(r'\[\w+\]', '', text).strip()

    def _filter_title_lines(self, text: str) -> str:
        """
        过滤文本中的 Markdown 标题行（# 开头的行）。
        
        Args:
            text: 原始文本
        
        Returns:
            str: 过滤后的文本
        """
        lines = text.split('\n')
        filtered_lines = [line for line in lines if not line.strip().startswith('#')]
        return '\n'.join(filtered_lines).strip()

    def _should_merge_audio(self, tts_engine: TTSInterface) -> bool:
        """
        检查是否应该启用音频合并功能。
        
        仅当同时满足以下条件时启用：
        1. lingxi_settings.audio_merge_enabled = True
        2. 当前使用的是 Step TTS 引擎
        
        Returns:
            bool: 是否启用音频合并
        """
        try:
            settings = get_lingxi_settings()
            audio_merge_enabled = settings.get("audio_merge_enabled", False)
            
            if not audio_merge_enabled:
                return False
            
            # 检查是否是 Step TTS 引擎
            engine_module = type(tts_engine).__module__
            is_step_tts = "step_tts" in engine_module
            
            if not is_step_tts:
                logger.debug(f"音频合并功能仅支持 Step TTS，当前引擎: {engine_module}")
                return False
            
            self._merge_max_sentences = settings.get("audio_merge_max_sentences", 3)
            self._progressive_merge_enabled = settings.get("progressive_merge_enabled", True)
            return True
            
        except Exception as e:
            logger.warning(f"检查音频合并设置时出错: {e}")
            return False

    async def speak(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        Queue a TTS task while maintaining order of delivery.

        Args:
            tts_text: Text to synthesize
            display_text: Text to display in UI
            actions: Live2D model actions
            live2d_model: Live2D model instance
            tts_engine: TTS engine instance
            websocket_send: WebSocket send function
        """
        # ========== 第一步：标题过滤 ==========
        # 检查 TTS 文本或显示文本是否以 # 开头（是标题）
        # 注意：双流模式下 tts_text 来自 <say>，display_text.text 来自 <show>
        display_text_str = display_text.text if isinstance(display_text, DisplayText) else str(display_text)
        
        if self._is_title_content(tts_text) or self._is_title_content(display_text_str):
            logger.info(f"🚫 跳过标题内容（不进入TTS）: tts='{tts_text[:50]}', display='{display_text_str[:50]}'")
            # 标题只显示，不生成音频，发送静音 payload
            await self._send_display_only(display_text, actions, websocket_send)
            return
        
        # ========== 第二步：情感标签过滤 ==========
        # 检查是否仅包含情感标签（如 [neutral]）
        if self._is_emotion_tag_only(tts_text):
            logger.info(f"🚫 跳过纯情感标签（不进入TTS）: '{tts_text}'")
            # 情感标签不显示也不朗读
            return
        
        # 移除文本中的情感标签
        filtered_tts_text = self._remove_emotion_tags(tts_text)
        
        # 过滤文本中嵌入的标题行
        filtered_tts_text = self._filter_title_lines(filtered_tts_text)
        
        # 如果过滤后文本为空，只显示不朗读
        if not filtered_tts_text.strip():
            logger.debug(f"过滤后文本为空，只显示: '{tts_text[:50]}...'")
            await self._send_display_only(display_text, actions, websocket_send)
            return
        
        # 检查是否为纯标点符号
        if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", filtered_tts_text)) == 0:
            logger.debug("空TTS文本（纯标点），发送静音显示")
            await self._send_display_only(display_text, actions, websocket_send)
            return

        # ========== 第二步：TTS 处理 ==========
        # 检查是否启用音频合并
        should_merge = self._should_merge_audio(tts_engine)
        
        if should_merge:
            await self._speak_with_merge(
                filtered_tts_text, display_text, actions, live2d_model, tts_engine, websocket_send
            )
        else:
            await self._speak_single(
                filtered_tts_text, display_text, actions, live2d_model, tts_engine, websocket_send
            )

    async def _send_display_only(
        self,
        display_text: DisplayText,
        actions: Optional[Actions],
        websocket_send: WebSocketSend,
    ) -> None:
        """
        发送仅显示的消息（无音频）。
        用于标题等不需要朗读的内容。
        """
        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        if not self._sender_task or self._sender_task.done():
            self._sender_task = asyncio.create_task(
                self._process_payload_queue(websocket_send)
            )

        await self._send_silent_payload(display_text, actions, current_sequence)

    async def _speak_with_merge(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        使用音频合并模式：累积多个句子后一起生成音频，减少 API 调用次数。
        
        渐进式合并（progressive_merge_enabled=True）：
        - 第1句：立即生成音频（缓冲大小=1）
        - 第2-3句：等待2句后合并生成（缓冲大小=2）
        - 第4句及以后：等待3句后合并生成（缓冲大小=3）
        
        这样可以确保首句快速响应，同时后续句子仍享受合并优化。
        
        重要：显示和音频是分离的：
        - 显示文本保持原样逐句显示
        - 音频合并后按字数比例分配播放时间
        """
        # 增加句子计数
        self._progressive_sentence_count += 1
        
        # 如果缓冲区为空，说明是新一轮合并的开始，锁定这一轮的 effective_max
        if len(self._merge_buffer) == 0:
            if self._progressive_merge_enabled:
                # 渐进式：基于当前句子数计算这一轮的缓冲大小
                self._current_round_max = min(self._progressive_sentence_count, self._merge_max_sentences)
            else:
                self._current_round_max = self._merge_max_sentences
            logger.debug(f"🔄 新一轮合并开始，有效缓冲大小: {self._current_round_max}")
        
        # 将当前句子加入缓冲区
        self._merge_buffer.append((tts_text, display_text, actions))
        
        logger.info(f"🔗 音频合并: 缓冲区累积 {len(self._merge_buffer)}/{self._current_round_max} 句 (渐进={self._progressive_merge_enabled}, 总句数={self._progressive_sentence_count})")
        
        # 如果缓冲区达到这一轮的有效最大句子数，执行合并生成
        if len(self._merge_buffer) >= self._current_round_max:
            if self._current_round_max == 1:
                logger.info(f"⚡ 渐进式合并: 首句立即响应")
            elif self._current_round_max < self._merge_max_sentences:
                logger.info(f"🔗 渐进式合并: 缓冲 {self._current_round_max} 句后生成")
            else:
                logger.info(f"🔗 音频合并: 达到最大句子数，开始合并生成")
            await self._flush_merge_buffer(live2d_model, tts_engine, websocket_send)

    def reset_for_new_conversation(self) -> None:
        """
        为新一轮对话重置状态。
        应在用户发送新消息时调用，以便渐进式合并从1开始。
        """
        self._progressive_sentence_count = 0
        logger.debug("🔄 TTS 管理器已重置，渐进式合并将从首句立即响应开始")

    async def flush_remaining(
        self,
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        刷新合并缓冲区中剩余的内容。
        应在对话结束时调用。
        """
        if self._merge_buffer:
            await self._flush_merge_buffer(live2d_model, tts_engine, websocket_send)

    async def _flush_merge_buffer(
        self,
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        将缓冲区中的句子合并后生成音频。
        
        关键：显示和音频分离处理
        - 每句话保持独立显示（保持原样式）
        - 音频合并为一个，然后按字数比例分配播放时间
        """
        if not self._merge_buffer:
            return
        
        buffer_copy = self._merge_buffer.copy()
        self._merge_buffer.clear()
        
        # 合并 TTS 文本
        merged_tts_text = "".join([item[0] for item in buffer_copy])
        
        # 计算每个句子的字数
        char_counts = [len(item[0]) for item in buffer_copy]
        total_chars = sum(char_counts)
        
        logger.info(f"🔗 音频合并: 合并 {len(buffer_copy)} 个句子, 总字数: {total_chars}")
        
        # Step TTS 串行生成合并音频
        audio_file_path = None
        total_duration_ms = 0
        
        try:
            audio_file_path = await tts_engine.async_generate_audio(
                text=merged_tts_text,
                file_name_no_ext=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
            )
            
            # 获取音频总时长
            total_duration_ms = get_audio_duration(audio_file_path)
            logger.info(f"🔗 合并音频生成完成, 时长: {total_duration_ms}ms")
            
        except Exception as e:
            logger.error(f"合并音频生成失败: {e}")
            # 失败时发送静音 payloads
            for tts_text, display_text, actions in buffer_copy:
                await self._send_display_only(display_text, actions, websocket_send)
            return
        
        try:
            # 读取音频数据
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_file_path)
            audio_bytes = audio.export(format="wav").read()
            import base64
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            
            # 计算音量数据
            from ..utils.stream_audio import _get_volume_by_chunks
            chunk_length_ms = 20
            volumes = _get_volume_by_chunks(audio, chunk_length_ms)
            
            # 按字数比例分配每句话的播放时间
            current_time_offset = 0
            
            for i, (tts_text, display_text, actions) in enumerate(buffer_copy):
                # 计算这句话的时长比例
                char_ratio = char_counts[i] / total_chars if total_chars > 0 else 1.0 / len(buffer_copy)
                sentence_duration_ms = int(total_duration_ms * char_ratio)
                
                # 计算这句话对应的音量切片
                start_volume_idx = int(current_time_offset / chunk_length_ms)
                end_volume_idx = int((current_time_offset + sentence_duration_ms) / chunk_length_ms)
                sentence_volumes = volumes[start_volume_idx:end_volume_idx] if start_volume_idx < len(volumes) else []
                
                logger.debug(f"🔗 句子 {i+1}: '{tts_text[:20]}...' 时长={sentence_duration_ms}ms, 字数比例={char_ratio:.2f}")
                
                # 构建这句话的 payload
                # 第一句携带完整音频，后续句子只携带显示信息和预计持续时间
                if i == 0:
                    # 第一句：携带完整音频
                    payload = {
                        "type": "audio",
                        "audio": audio_base64,
                        "volumes": volumes,  # 完整音量数据
                        "slice_length": chunk_length_ms,
                        "display_text": display_text.to_dict() if isinstance(display_text, DisplayText) else display_text,
                        "actions": actions.to_dict() if actions else None,
                        "forwarded": False,
                        # 额外信息：用于前端分段显示
                        "merge_info": {
                            "is_merged": True,
                            "total_sentences": len(buffer_copy),
                            "sentence_index": i,
                            "sentence_duration_ms": sentence_duration_ms,
                            "total_duration_ms": total_duration_ms,
                        }
                    }
                else:
                    # 后续句子：不携带音频，只携带显示信息和计时信息
                    payload = {
                        "type": "audio",
                        "audio": None,  # 无音频
                        "volumes": sentence_volumes,  # 部分音量数据用于口型同步
                        "slice_length": chunk_length_ms,
                        "display_text": display_text.to_dict() if isinstance(display_text, DisplayText) else display_text,
                        "actions": actions.to_dict() if actions else None,
                        "forwarded": False,
                        "merge_info": {
                            "is_merged": True,
                            "total_sentences": len(buffer_copy),
                            "sentence_index": i,
                            "sentence_duration_ms": sentence_duration_ms,
                            "delay_before_show_ms": current_time_offset,  # 显示前延迟
                            "total_duration_ms": total_duration_ms,
                        }
                    }
                
                await websocket_send(json.dumps(payload))
                current_time_offset += sentence_duration_ms
                
        except Exception as e:
            logger.error(f"处理合并音频 payload 失败: {e}")
            # 失败时发送静音 payloads
            for tts_text, display_text, actions in buffer_copy:
                await self._send_display_only(display_text, actions, websocket_send)
        finally:
            if audio_file_path:
                tts_engine.remove_file(audio_file_path)
                logger.debug("合并音频缓存文件已清理")

    async def _speak_serial(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        串行 TTS 模式：直接执行 TTS 并等待完成，不创建并发任务。
        用于 Step TTS 等不支持并发的引擎。
        """
        logger.debug(
            f"🏃 串行 TTS 生成: '''{tts_text[:50]}...''' (by {display_text.name})"
        )
        
        audio_file_path = None
        try:
            # 直接生成音频（不创建并发任务）
            audio_file_path = await tts_engine.async_generate_audio(
                text=tts_text,
                file_name_no_ext=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
            )
            
            # 准备并发送 payload
            payload = prepare_audio_payload(
                audio_path=audio_file_path,
                display_text=display_text,
                actions=actions,
            )
            await websocket_send(json.dumps(payload))
            
        except Exception as e:
            logger.error(f"串行 TTS 生成失败: {e}")
            # 发送静音 payload
            payload = prepare_audio_payload(
                audio_path=None,
                display_text=display_text,
                actions=actions,
            )
            await websocket_send(json.dumps(payload))
        finally:
            if audio_file_path:
                tts_engine.remove_file(audio_file_path)
                logger.debug("音频缓存文件已清理")

    async def _speak_single(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        单句 TTS 模式（原有逻辑）。
        """
        logger.debug(
            f"🏃Queuing TTS task for: '''{tts_text}''' (by {display_text.name})"
        )

        # Get current sequence number
        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        # Start sender task if not running
        if not self._sender_task or self._sender_task.done():
            self._sender_task = asyncio.create_task(
                self._process_payload_queue(websocket_send)
            )

        # Create and queue the TTS task
        task = asyncio.create_task(
            self._process_tts(
                tts_text=tts_text,
                display_text=display_text,
                actions=actions,
                live2d_model=live2d_model,
                tts_engine=tts_engine,
                sequence_number=current_sequence,
            )
        )
        self.task_list.append(task)

    async def _process_payload_queue(self, websocket_send: WebSocketSend) -> None:
        """
        Process and send payloads in correct order.
        Runs continuously until all payloads are processed.
        """
        buffered_payloads: Dict[int, Dict] = {}

        while True:
            try:
                # Get payload from queue
                payload, sequence_number = await self._payload_queue.get()
                buffered_payloads[sequence_number] = payload

                # Send payloads in order
                while self._next_sequence_to_send in buffered_payloads:
                    next_payload = buffered_payloads.pop(self._next_sequence_to_send)
                    await websocket_send(json.dumps(next_payload))
                    self._next_sequence_to_send += 1

                self._payload_queue.task_done()

            except asyncio.CancelledError:
                break

    async def _send_silent_payload(
        self,
        display_text: DisplayText,
        actions: Optional[Actions],
        sequence_number: int,
    ) -> None:
        """Queue a silent audio payload"""
        audio_payload = prepare_audio_payload(
            audio_path=None,
            display_text=display_text,
            actions=actions,
        )
        await self._payload_queue.put((audio_payload, sequence_number))

    async def _process_tts(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        tts_engine: TTSInterface,
        sequence_number: int,
    ) -> None:
        """Process TTS generation and queue the result for ordered delivery"""
        audio_file_path = None
        try:
            audio_file_path = await self._generate_audio(tts_engine, tts_text)
            payload = prepare_audio_payload(
                audio_path=audio_file_path,
                display_text=display_text,
                actions=actions,
            )
            # Queue the payload with its sequence number
            await self._payload_queue.put((payload, sequence_number))

        except Exception as e:
            logger.error(f"Error preparing audio payload: {e}")
            # Queue silent payload for error case
            payload = prepare_audio_payload(
                audio_path=None,
                display_text=display_text,
                actions=actions,
            )
            await self._payload_queue.put((payload, sequence_number))

        finally:
            if audio_file_path:
                tts_engine.remove_file(audio_file_path)
                logger.debug("Audio cache file cleaned.")

    async def _generate_audio(self, tts_engine: TTSInterface, text: str) -> str:
        """Generate audio file from text"""
        logger.debug(f"🏃Generating audio for '''{text}'''...")
        return await tts_engine.async_generate_audio(
            text=text,
            file_name_no_ext=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
        )

    def clear(self) -> None:
        """Clear all pending tasks and reset state"""
        self.task_list.clear()
        if self._sender_task:
            self._sender_task.cancel()
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        # Create a new queue to clear any pending items
        self._payload_queue = asyncio.Queue()
        # 清空合并缓冲区
        self._merge_buffer.clear()
