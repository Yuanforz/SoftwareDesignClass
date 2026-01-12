import asyncio
import json
from typing import Dict, Optional, Callable

import numpy as np
from fastapi import WebSocket
from loguru import logger

from ..chat_group import ChatGroupManager
from ..chat_history_manager import store_message
from ..service_context import ServiceContext
from .group_conversation import process_group_conversation
from .single_conversation import process_single_conversation
from .conversation_utils import EMOJI_LIST
from .types import GroupConversationState
from prompts import prompt_loader


async def handle_conversation_trigger(
    msg_type: str,
    data: dict,
    client_uid: str,
    context: ServiceContext,
    websocket: WebSocket,
    client_contexts: Dict[str, ServiceContext],
    client_connections: Dict[str, WebSocket],
    chat_group_manager: ChatGroupManager,
    received_data_buffers: Dict[str, np.ndarray],
    current_conversation_tasks: Dict[str, Optional[asyncio.Task]],
    broadcast_to_group: Callable,
) -> None:
    """Handle triggers that start a conversation"""
    metadata = None

    if msg_type == "ai-speak-signal":
        try:
            # Get proactive speak prompt from config
            prompt_name = "proactive_speak_prompt"
            prompt_file = context.system_config.tool_prompts.get(prompt_name)
            if prompt_file:
                user_input = prompt_loader.load_util(prompt_file)
            else:
                logger.warning("Proactive speak prompt not configured, using default")
                user_input = "Please say something."
        except Exception as e:
            logger.error(f"Error loading proactive speak prompt: {e}")
            user_input = "Please say something."

        # Add metadata to indicate this is a proactive speak request
        # that should be skipped in both memory and history
        metadata = {
            "proactive_speak": True,
            "skip_memory": True,  # Skip storing in AI's internal memory
            "skip_history": True,  # Skip storing in local conversation history
        }

        await websocket.send_text(
            json.dumps(
                {
                    "type": "full-text",
                    "text": "AI wants to speak something...",
                }
            )
        )
    elif msg_type == "text-input":
        user_input = data.get("text", "")
    else:  # mic-audio-end
        user_input = received_data_buffers[client_uid]
        received_data_buffers[client_uid] = np.array([])

    # 获取唤醒词配置（仅语音输入时有效）
    wake_word_config = data.get("wake_word_config", None)
    if wake_word_config:
        logger.info(f"Wake word config: enabled={wake_word_config.get('enabled')}, words={wake_word_config.get('words')}")

    # 获取停止词配置（仅语音输入时有效，用于语音打断）
    stop_word_config = data.get("stop_word_config", None)
    if stop_word_config:
        logger.info(f"Stop word config: enabled={stop_word_config.get('enabled')}, words={stop_word_config.get('words')}")

    # 停止词早期检测：如果是语音输入且启用了停止词，先进行 ASR 检测
    # 如果检测到停止词，直接触发打断而不是启动新对话
    pre_transcribed_text = None  # 预转录的文本，避免 single_conversation 重复 ASR
    if msg_type == "mic-audio-end" and stop_word_config and stop_word_config.get("enabled", False):
        stop_words = stop_word_config.get("words", [])
        fuzzy_pinyin = stop_word_config.get("fuzzy_pinyin", False)
        
        if stop_words and isinstance(user_input, np.ndarray) and len(user_input) > 0:
            # 先进行语音识别
            try:
                transcribed_text = await context.asr_engine.async_transcribe_np(user_input)
                if transcribed_text:
                    transcribed_text = transcribed_text.strip()
                    pre_transcribed_text = transcribed_text  # 保存结果供后续使用
                    logger.info(f"Stop word early check - ASR result: '{transcribed_text}'")
                    
                    # 检测停止词
                    from .conversation_utils import check_stop_word
                    result = check_stop_word(transcribed_text, stop_words, fuzzy_pinyin)
                    
                    if result["has_stop_word"]:
                        matched_word = result["matched_word"]
                        logger.info(f"🛑 Stop word '{matched_word}' detected early, triggering interrupt instead of new conversation")
                        
                        # 清空音频接收缓冲区
                        if client_uid in received_data_buffers:
                            received_data_buffers[client_uid] = np.array([])
                            logger.info(f"🧹 Cleared audio buffer for client {client_uid}")
                        
                        # 发送识别结果给前端（标记为停止词）
                        await websocket.send_text(
                            json.dumps({
                                "type": "user-input-transcription",
                                "text": f"（停止词：{matched_word}）",
                                "original_text": transcribed_text,
                                "is_stop_word": True
                            })
                        )
                        
                        # 直接触发打断处理（取消当前正在进行的对话任务）
                        await handle_individual_interrupt(
                            client_uid=client_uid,
                            current_conversation_tasks=current_conversation_tasks,
                            context=context,
                            heard_response="",  # 被打断的响应，这里为空
                        )
                        
                        # 发送打断控制信号给前端
                        await websocket.send_text(
                            json.dumps({"type": "control", "text": "interrupt"})
                        )
                        
                        # 不启动新对话，直接返回
                        return
            except Exception as e:
                logger.error(f"Stop word early check failed: {e}")
                # 失败时继续正常流程

    # 处理图片数据：将前端发送的 base64 字符串数组转换为后端期望的格式
    raw_images = data.get("images")
    images = None
    if raw_images:
        images = []
        for img in raw_images:
            if isinstance(img, str):
                # 前端发送的是 base64 data URL 字符串
                # 需要转换为 {"source": "upload", "data": ..., "mime_type": ...} 格式
                mime_type = "image/png"  # 默认
                if img.startswith("data:"):
                    # 解析 data URL 获取 MIME 类型
                    # 格式: data:image/png;base64,xxxxx
                    try:
                        header = img.split(",")[0]
                        if ":" in header and ";" in header:
                            mime_type = header.split(":")[1].split(";")[0]
                    except Exception:
                        pass
                images.append({
                    "source": "upload",
                    "data": img,
                    "mime_type": mime_type
                })
            elif isinstance(img, dict):
                # 已经是正确的格式
                images.append(img)
        
        if images:
            logger.info(f"Received {len(images)} images from client")
    
    session_emoji = np.random.choice(EMOJI_LIST)

    group = chat_group_manager.get_client_group(client_uid)
    if group and len(group.members) > 1:
        # Use group_id as task key for group conversations
        task_key = group.group_id
        if (
            task_key not in current_conversation_tasks
            or current_conversation_tasks[task_key].done()
        ):
            logger.info(f"Starting new group conversation for {task_key}")

            current_conversation_tasks[task_key] = asyncio.create_task(
                process_group_conversation(
                    client_contexts=client_contexts,
                    client_connections=client_connections,
                    broadcast_func=broadcast_to_group,
                    group_members=group.members,
                    initiator_client_uid=client_uid,
                    user_input=user_input,
                    images=images,
                    session_emoji=session_emoji,
                    metadata=metadata,
                )
            )
    else:
        # Use client_uid as task key for individual conversations
        current_conversation_tasks[client_uid] = asyncio.create_task(
            process_single_conversation(
                context=context,
                websocket_send=websocket.send_text,
                client_uid=client_uid,
                user_input=user_input,
                images=images,
                session_emoji=session_emoji,
                metadata=metadata,
                wake_word_config=wake_word_config,
                stop_word_config=stop_word_config,
                pre_transcribed_text=pre_transcribed_text,  # 预转录文本，避免重复 ASR
            )
        )


async def handle_individual_interrupt(
    client_uid: str,
    current_conversation_tasks: Dict[str, Optional[asyncio.Task]],
    context: ServiceContext,
    heard_response: str,
):
    """处理单用户对话打断
    
    执行以下清理操作：
    1. 取消正在进行的对话任务（停止 LLM 生成和 TTS 合成）
    2. 通知 agent_engine 处理打断（更新内存/历史）
    3. 重置 agent_engine 的打断标志
    4. 记录打断到历史
    """
    logger.info(f"🛑 Processing interrupt for client {client_uid}")
    
    if client_uid in current_conversation_tasks:
        task = current_conversation_tasks[client_uid]
        if task and not task.done():
            # 取消任务会触发 CancelledError，终止所有正在进行的异步操作
            task.cancel()
            # 等待任务真正被取消
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            logger.info("🛑 Conversation task was successfully interrupted")
        
        # 清除任务引用
        current_conversation_tasks[client_uid] = None

    # 通知 agent_engine 处理打断
    try:
        context.agent_engine.handle_interrupt(heard_response)
        # 重置打断标志，为下一次对话做准备
        if hasattr(context.agent_engine, 'reset_interrupt'):
            context.agent_engine.reset_interrupt()
            logger.debug("Agent interrupt flag reset")
    except Exception as e:
        logger.error(f"Error handling interrupt: {e}")

    # 记录打断到历史
    if context.history_uid and heard_response:
        store_message(
            conf_uid=context.character_config.conf_uid,
            history_uid=context.history_uid,
            role="ai",
            content=heard_response,
            name=context.character_config.character_name,
            avatar=context.character_config.avatar,
        )
        store_message(
            conf_uid=context.character_config.conf_uid,
            history_uid=context.history_uid,
            role="system",
            content="[Interrupted by user]",
        )
    
    logger.info(f"✅ Interrupt handling complete for client {client_uid}")


async def handle_group_interrupt(
    group_id: str,
    heard_response: str,
    current_conversation_tasks: Dict[str, Optional[asyncio.Task]],
    chat_group_manager: ChatGroupManager,
    client_contexts: Dict[str, ServiceContext],
    broadcast_to_group: Callable,
) -> None:
    """Handles interruption for a group conversation"""
    task = current_conversation_tasks.get(group_id)
    if not task or task.done():
        return

    # Get state and speaker info before cancellation
    state = GroupConversationState.get_state(group_id)
    current_speaker_uid = state.current_speaker_uid if state else None

    # Get context from current speaker
    context = None
    group = chat_group_manager.get_group_by_id(group_id)
    if current_speaker_uid:
        context = client_contexts.get(current_speaker_uid)
        logger.info(f"Found current speaker context for {current_speaker_uid}")
    if not context and group and group.members:
        logger.warning(f"No context found for group {group_id}, using first member")
        context = client_contexts.get(next(iter(group.members)))

    # Now cancel the task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info(f"🛑 Group conversation {group_id} cancelled successfully.")

    current_conversation_tasks.pop(group_id, None)
    GroupConversationState.remove_state(group_id)  # Clean up state after we've used it

    # Store messages with speaker info
    if context and group:
        for member_uid in group.members:
            if member_uid in client_contexts:
                try:
                    member_ctx = client_contexts[member_uid]
                    member_ctx.agent_engine.handle_interrupt(heard_response)
                    store_message(
                        conf_uid=member_ctx.character_config.conf_uid,
                        history_uid=member_ctx.history_uid,
                        role="ai",
                        content=heard_response,
                        name=context.character_config.character_name,
                        avatar=context.character_config.avatar,
                    )
                    store_message(
                        conf_uid=member_ctx.character_config.conf_uid,
                        history_uid=member_ctx.history_uid,
                        role="system",
                        content="[Interrupted by user]",
                    )
                except Exception as e:
                    logger.error(f"Error handling interrupt for {member_uid}: {e}")

    await broadcast_to_group(
        list(group.members),
        {
            "type": "interrupt-signal",
            "text": "conversation-interrupted",
        },
    )
