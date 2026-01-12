import asyncio
import re
from typing import Optional, Union, Any, List, Dict
import numpy as np
import json
from loguru import logger

from ..message_handler import message_handler
from .types import WebSocketSend, BroadcastContext
from .tts_manager import TTSTaskManager
from ..agent.output_types import SentenceOutput, AudioOutput
from ..agent.input_types import BatchInput, TextData, ImageData, TextSource, ImageSource
from ..asr.asr_interface import ASRInterface
from ..live2d_model import Live2dModel
from ..tts.tts_interface import TTSInterface
from ..utils.stream_audio import prepare_audio_payload


# Convert class methods to standalone functions
def create_batch_input(
    input_text: str,
    images: Optional[List[Dict[str, Any]]],
    from_name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> BatchInput:
    """Create batch input for agent processing"""
    return BatchInput(
        texts=[
            TextData(source=TextSource.INPUT, content=input_text, from_name=from_name)
        ],
        images=[
            ImageData(
                source=ImageSource(img["source"]),
                data=img["data"],
                mime_type=img["mime_type"],
            )
            for img in (images or [])
        ]
        if images
        else None,
        metadata=metadata,
    )


async def process_agent_output(
    output: Union[AudioOutput, SentenceOutput],
    character_config: Any,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
) -> str:
    """Process agent output with character information and optional translation"""
    output.display_text.name = character_config.character_name
    output.display_text.avatar = character_config.avatar

    full_response = ""
    try:
        if isinstance(output, SentenceOutput):
            full_response = await handle_sentence_output(
                output,
                live2d_model,
                tts_engine,
                websocket_send,
                tts_manager,
            )
        elif isinstance(output, AudioOutput):
            full_response = await handle_audio_output(output, websocket_send)
        else:
            logger.warning(f"Unknown output type: {type(output)}")
    except Exception as e:
        logger.error(f"Error processing agent output: {e}")
        await websocket_send(
            json.dumps(
                {"type": "error", "message": f"Error processing response: {str(e)}"}
            )
        )

    return full_response


async def handle_sentence_output(
    output: SentenceOutput,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
) -> str:
    """Handle sentence output type with optional translation support"""
    full_response = ""
    async for display_text, tts_text, actions in output:
        logger.debug(f"🏃 Processing output: '''{tts_text}'''...")

        full_response += display_text.text
        await tts_manager.speak(
            tts_text=tts_text,
            display_text=display_text,
            actions=actions,
            live2d_model=live2d_model,
            tts_engine=tts_engine,
            websocket_send=websocket_send,
        )
    
    # 注意：flush_remaining 应在整个对话结束时调用，而不是每个 SentenceOutput 处理完后
    # 因为 agent.chat 会产生多个 SentenceOutput，每个只包含一个句子
    
    return full_response


async def handle_audio_output(
    output: AudioOutput,
    websocket_send: WebSocketSend,
) -> str:
    """Process and send AudioOutput directly to the client"""
    full_response = ""
    async for audio_path, display_text, transcript, actions in output:
        full_response += transcript
        audio_payload = prepare_audio_payload(
            audio_path=audio_path,
            display_text=display_text,
            actions=actions.to_dict() if actions else None,
        )
        await websocket_send(json.dumps(audio_payload))
    return full_response


async def send_conversation_start_signals(websocket_send: WebSocketSend) -> None:
    """Send initial conversation signals"""
    await websocket_send(
        json.dumps(
            {
                "type": "control",
                "text": "conversation-chain-start",
            }
        )
    )
    await websocket_send(json.dumps({"type": "full-text", "text": "Thinking..."}))


async def process_user_input(
    user_input: Union[str, np.ndarray],
    asr_engine: ASRInterface,
    websocket_send: WebSocketSend,
    wake_word_config: Optional[dict] = None,
    stop_word_config: Optional[dict] = None,
    is_from_voice: bool = False,
) -> str:
    """Process user input, converting audio to text if needed.
    
    Args:
        user_input: Audio data (np.ndarray) or text string
        asr_engine: ASR engine for transcription
        websocket_send: WebSocket send function
        wake_word_config: Optional wake word configuration
            - enabled: bool - whether wake word detection is enabled
            - words: list[str] - list of wake words to detect
        stop_word_config: Optional stop word configuration (for interrupting AI)
            - enabled: bool - whether stop word detection is enabled
            - words: list[str] - list of stop words to detect
            - fuzzy_pinyin: bool - whether to use pinyin matching
        is_from_voice: Whether input originally came from voice (for pre-transcribed text)
    
    Returns:
        str: The processed text input. Returns empty string if:
            - Audio transcription failed or returned empty
            - Input text was empty after stripping
            - Wake word is enabled but not detected
        Returns "__STOP_WORD__" if stop word is detected (caller should send interrupt signal)
    """
    if isinstance(user_input, np.ndarray):
        logger.info("Transcribing audio input...")
        input_text = await asr_engine.async_transcribe_np(user_input)
        
        # 清理和验证识别结果
        if input_text:
            input_text = input_text.strip()
        
        # 检查是否为有效文本
        if not input_text or len(input_text) == 0:
            logger.warning("ASR returned empty or invalid text, skipping conversation")
            return ""
        
        # 过滤掉一些常见的无效识别结果
        invalid_patterns = [
            "。", ".", "，", ",", "!", "?",  # 单个标点
            "嗯", "啊", "哦", "呃",  # 单个语气词
        ]
        if input_text in invalid_patterns:
            logger.warning(f"ASR returned noise-like text: '{input_text}', skipping")
            return ""
        
        # 停止词检测（优先级高于唤醒词）
        if stop_word_config and stop_word_config.get("enabled", False):
            stop_words = stop_word_config.get("words", [])
            fuzzy_pinyin = stop_word_config.get("fuzzy_pinyin", False)
            if stop_words:
                result = check_stop_word(input_text, stop_words, fuzzy_pinyin)
                if result["has_stop_word"]:
                    matched_word = result["matched_word"]
                    logger.info(f"Stop word '{matched_word}' detected in: '{input_text}', triggering interrupt")
                    # 发送原始文本给前端，让前端知道检测到了停止词
                    await websocket_send(
                        json.dumps({
                            "type": "user-input-transcription", 
                            "text": f"（停止词：{matched_word}）",
                            "original_text": input_text,
                            "is_stop_word": True
                        })
                    )
                    return "__STOP_WORD__"
        
        # 唤醒词检测
        if wake_word_config and wake_word_config.get("enabled", False):
            wake_words = wake_word_config.get("words", [])
            fuzzy_pinyin = wake_word_config.get("fuzzy_pinyin", False)
            if wake_words:
                result = check_wake_word(input_text, wake_words, fuzzy_pinyin)
                if result["has_wake_word"]:
                    clean_text = result["clean_text"]
                    matched_word = result["matched_word"]
                    logger.info(f"Wake word '{matched_word}' detected, question: '{clean_text}'")
                    
                    if clean_text:
                        # 发送识别结果（已去掉唤醒词）
                        await websocket_send(
                            json.dumps({"type": "user-input-transcription", "text": clean_text})
                        )
                        return clean_text
                    else:
                        # 只说了唤醒词，没有后续内容
                        logger.info(f"Only wake word '{matched_word}' detected, waiting for more input")
                        await websocket_send(
                            json.dumps({"type": "user-input-transcription", "text": f"（唤醒词：{matched_word}）"})
                        )
                        return ""
                else:
                    # 没有检测到唤醒词
                    logger.info(f"Wake word not detected in: '{input_text}', skipping")
                    # 不发送识别结果，静默忽略
                    return ""
        
        await websocket_send(
            json.dumps({"type": "user-input-transcription", "text": input_text})
        )
        return input_text
    
    # 文本输入处理
    if isinstance(user_input, str):
        input_text = user_input.strip()
        
        # 如果来自语音（预转录文本），需要执行唤醒词检测
        if is_from_voice and input_text:
            # 唤醒词检测
            if wake_word_config and wake_word_config.get("enabled", False):
                wake_words = wake_word_config.get("words", [])
                fuzzy_pinyin = wake_word_config.get("fuzzy_pinyin", False)
                if wake_words:
                    result = check_wake_word(input_text, wake_words, fuzzy_pinyin)
                    if result["has_wake_word"]:
                        clean_text = result["clean_text"]
                        matched_word = result["matched_word"]
                        logger.info(f"Wake word '{matched_word}' detected (pre-transcribed), question: '{clean_text}'")
                        
                        if clean_text:
                            # 发送识别结果（已去掉唤醒词）
                            await websocket_send(
                                json.dumps({"type": "user-input-transcription", "text": clean_text})
                            )
                            return clean_text
                        else:
                            # 只说了唤醒词，没有后续内容
                            logger.info(f"Only wake word '{matched_word}' detected, waiting for more input")
                            await websocket_send(
                                json.dumps({"type": "user-input-transcription", "text": f"（唤醒词：{matched_word}）"})
                            )
                            return ""
                    else:
                        # 没有检测到唤醒词
                        logger.info(f"Wake word not detected in pre-transcribed: '{input_text}', skipping")
                        # 不发送识别结果，静默忽略
                        return ""
            
            # 没有启用唤醒词，发送转录结果并返回
            await websocket_send(
                json.dumps({"type": "user-input-transcription", "text": input_text})
            )
        
        return input_text
    
    return user_input


def check_wake_word(text: str, wake_words: list, fuzzy_pinyin: bool = False) -> dict:
    """检查文本是否包含唤醒词
    
    Args:
        text: 要检查的文本
        wake_words: 唤醒词列表
        fuzzy_pinyin: 是否启用拼音模糊匹配
        
    Returns:
        dict: {
            "has_wake_word": bool,
            "matched_word": str,
            "clean_text": str
        }
    """
    import re
    normalized_text = text.lower().strip()
    
    # 如果启用拼音模糊匹配，尝试导入 pypinyin
    pinyin_available = False
    if fuzzy_pinyin:
        try:
            from pypinyin import lazy_pinyin
            pinyin_available = True
            # 将文本转换为拼音
            text_pinyin = ''.join(lazy_pinyin(normalized_text))
            logger.debug(f"Pinyin conversion: '{normalized_text}' -> '{text_pinyin}'")
        except ImportError:
            logger.warning("pypinyin not installed, falling back to exact matching")
            pinyin_available = False
    
    for wake_word in wake_words:
        normalized_wake_word = wake_word.lower().strip()
        
        # 精确匹配：检查文本是否以唤醒词开头
        if normalized_text.startswith(normalized_wake_word):
            # 去掉唤醒词和可能的分隔符
            clean_text = text[len(wake_word):].strip()
            clean_text = re.sub(r'^[,，、。.!！?？\s]+', '', clean_text).strip()
            
            return {
                "has_wake_word": True,
                "matched_word": wake_word,
                "clean_text": clean_text
            }
        
        # 精确匹配：检查文本中间是否包含唤醒词
        wake_word_index = normalized_text.find(normalized_wake_word)
        if wake_word_index != -1:
            clean_text = text[wake_word_index + len(wake_word):].strip()
            clean_text = re.sub(r'^[,，、。.!！?？\s]+', '', clean_text).strip()
            
            return {
                "has_wake_word": True,
                "matched_word": wake_word,
                "clean_text": clean_text
            }
        
        # 拼音模糊匹配
        if fuzzy_pinyin and pinyin_available:
            wake_word_pinyin = ''.join(lazy_pinyin(normalized_wake_word))
            logger.debug(f"Wake word pinyin: '{normalized_wake_word}' -> '{wake_word_pinyin}'")
            
            # 检查拼音是否匹配
            pinyin_index = text_pinyin.find(wake_word_pinyin)
            if pinyin_index != -1:
                # 找到拼音匹配位置后，需要计算原文中对应的位置
                # 逐字符累积拼音长度来定位
                char_index = 0
                pinyin_len_so_far = 0
                
                for i, char in enumerate(normalized_text):
                    char_pinyin = ''.join(lazy_pinyin(char))
                    if pinyin_len_so_far >= pinyin_index:
                        char_index = i
                        break
                    pinyin_len_so_far += len(char_pinyin)
                
                # 计算唤醒词在原文中的结束位置
                end_index = char_index
                pinyin_len_of_word = 0
                for i in range(char_index, len(normalized_text)):
                    char_pinyin = ''.join(lazy_pinyin(normalized_text[i]))
                    pinyin_len_of_word += len(char_pinyin)
                    if pinyin_len_of_word >= len(wake_word_pinyin):
                        end_index = i + 1
                        break
                
                clean_text = text[end_index:].strip()
                clean_text = re.sub(r'^[,，、。.!！?？\s]+', '', clean_text).strip()
                
                matched_original = text[char_index:end_index]
                logger.info(f"Pinyin match: '{wake_word}' ({wake_word_pinyin}) matched '{matched_original}' in text")
                
                return {
                    "has_wake_word": True,
                    "matched_word": f"{wake_word}(~{matched_original})",
                    "clean_text": clean_text
                }
    
    return {
        "has_wake_word": False,
        "matched_word": "",
        "clean_text": text
    }


def check_stop_word(text: str, stop_words: list, fuzzy_pinyin: bool = False) -> dict:
    """检查文本是否包含停止词（用于语音打断）
    
    停止词检测比唤醒词更宽松：只要文本包含停止词就触发
    
    Args:
        text: 要检查的文本
        stop_words: 停止词列表
        fuzzy_pinyin: 是否启用拼音模糊匹配
        
    Returns:
        dict: {
            "has_stop_word": bool,
            "matched_word": str
        }
    """
    normalized_text = text.lower().strip()
    
    # 如果启用拼音模糊匹配，尝试导入 pypinyin
    pinyin_available = False
    text_pinyin = ""
    if fuzzy_pinyin:
        try:
            from pypinyin import lazy_pinyin
            pinyin_available = True
            # 将文本转换为拼音
            text_pinyin = ''.join(lazy_pinyin(normalized_text))
            logger.debug(f"Stop word pinyin check: '{normalized_text}' -> '{text_pinyin}'")
        except ImportError:
            logger.warning("pypinyin not installed, falling back to exact matching")
            pinyin_available = False
    
    for stop_word in stop_words:
        normalized_stop_word = stop_word.lower().strip()
        if not normalized_stop_word:
            continue
        
        # 精确匹配：整个文本就是停止词，或文本包含停止词
        if normalized_text == normalized_stop_word or normalized_stop_word in normalized_text:
            logger.info(f"Stop word exact match: '{stop_word}' in '{text}'")
            return {
                "has_stop_word": True,
                "matched_word": stop_word
            }
        
        # 拼音模糊匹配
        if fuzzy_pinyin and pinyin_available:
            stop_word_pinyin = ''.join(lazy_pinyin(normalized_stop_word))
            
            # 检查拼音是否匹配
            if text_pinyin == stop_word_pinyin or stop_word_pinyin in text_pinyin:
                logger.info(f"Stop word pinyin match: '{stop_word}' ({stop_word_pinyin}) in '{text}' ({text_pinyin})")
                return {
                    "has_stop_word": True,
                    "matched_word": stop_word
                }
    
    return {
        "has_stop_word": False,
        "matched_word": ""
    }


async def finalize_conversation_turn(
    tts_manager: TTSTaskManager,
    websocket_send: WebSocketSend,
    client_uid: str,
    broadcast_ctx: Optional[BroadcastContext] = None,
) -> None:
    """Finalize a conversation turn"""
    if tts_manager.task_list:
        await asyncio.gather(*tts_manager.task_list)
        await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        response = await message_handler.wait_for_response(
            client_uid, "frontend-playback-complete"
        )

        if not response:
            logger.warning(f"No playback completion response from {client_uid}")
            return

    await websocket_send(json.dumps({"type": "force-new-message"}))

    if broadcast_ctx and broadcast_ctx.broadcast_func:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            {"type": "force-new-message"},
            broadcast_ctx.current_client_uid,
        )

    await send_conversation_end_signal(websocket_send, broadcast_ctx)


async def send_conversation_end_signal(
    websocket_send: WebSocketSend,
    broadcast_ctx: Optional[BroadcastContext],
    session_emoji: str = "😊",
) -> None:
    """Send conversation chain end signal"""
    chain_end_msg = {
        "type": "control",
        "text": "conversation-chain-end",
    }

    await websocket_send(json.dumps(chain_end_msg))

    if broadcast_ctx and broadcast_ctx.broadcast_func and broadcast_ctx.group_members:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            chain_end_msg,
        )

    logger.info(f"😎👍✅ Conversation Chain {session_emoji} completed!")


def cleanup_conversation(tts_manager: TTSTaskManager, session_emoji: str) -> None:
    """Clean up conversation resources"""
    tts_manager.clear()
    logger.debug(f"🧹 Clearing up conversation {session_emoji}.")


EMOJI_LIST = [
    "🐶",
    "🐱",
    "🐭",
    "🐹",
    "🐰",
    "🦊",
    "🐻",
    "🐼",
    "🐨",
    "🐯",
    "🦁",
    "🐮",
    "🐷",
    "🐸",
    "🐵",
    "🐔",
    "🐧",
    "🐦",
    "🐤",
    "🐣",
    "🐥",
    "🦆",
    "🦅",
    "🦉",
    "🦇",
    "🐺",
    "🐗",
    "🐴",
    "🦄",
    "🐝",
    "🌵",
    "🎄",
    "🌲",
    "🌳",
    "🌴",
    "🌱",
    "🌿",
    "☘️",
    "🍀",
    "🍂",
    "🍁",
    "🍄",
    "🌾",
    "💐",
    "🌹",
    "🌸",
    "🌛",
    "🌍",
    "⭐️",
    "🔥",
    "🌈",
    "🌩",
    "⛄️",
    "🎃",
    "🎄",
    "🎉",
    "🎏",
    "🎗",
    "🀄️",
    "🎭",
    "🎨",
    "🧵",
    "🪡",
    "🧶",
    "🥽",
    "🥼",
    "🦺",
    "👔",
    "👕",
    "👜",
    "👑",
]
