from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot_plugin_alconna import CommandResult, UniMessage, UniMsg
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import Video as UniVideo
from nonebot_plugin_alconna.uniseg import Voice as UniVoice

from zhenxun.services.llm import (
    LLMMessage,
    get_model_instance,
    message_to_unimessage,
    unimsg_to_llm_parts,
)
from zhenxun.services.llm.types import get_user_friendly_error_message
from zhenxun.services.log import logger

from .. import ai
from ..config import CHINESE_CHAR_THRESHOLD, base_config
from ..core import get_current_active_model_name
from ..core.agent_loop import run_generic_agent_loop
from ..core.session_manager import (
    SessionStatus,
    session_manager,
)
from ..tools import (
    MCP_AVAILABLE,
    detect_function_calling_intent_with_ai,
    detect_intent_by_keywords,
)
from ..utils.converters import convert_to_image

MARKDOWN_STYLING_PROMPT = """
注意使用丰富的markdown格式让内容更美观，注意要在合适的场景使用合适的样式,不合适就不使用,包括：
标题层级(h1-h6)、粗体(bold)、斜体(em)、引用块(blockquote)、
有序列表(ordered list)、无序列表(unordered list)、任务列表(checkbox)、
代码块(code)、内联代码(inline code)、表格(table)、分隔线(hr)、
删除线(Strikethrough)、链接(links)、嵌套列表(nested lists)、emoji增强格式(emoji-enhanced formatting)、
Mermaid图表(graph td)等。
""".strip()


AGENT_CONFIGS = {
    "MAP": {
        "tool_name": "baidu-map",
        "system_prompt": """你是专业的地理和路线规划助手，拥有百度地图功能。

核心功能：
• 地址坐标转换（地址↔坐标）
• 地点查询（POI检索、详情获取）
• 路线规划（多种出行方式、距离时间）
• 实时信息（路况、天气、定位）

重要提醒：
- 必须使用工具获取实时准确信息，不要凭记忆回答
- 工具失败时说明原因并提供建议
- 用中文回复，格式清晰，包含关键信息

{MARKDOWN_STYLING_PROMPT}""",
    },
}


async def _prepare_final_response(response: str | bytes) -> str | MessageSegment:
    """统一处理最终的响应，准备待发送的消息段，包括Markdown转图片逻辑"""
    if isinstance(response, bytes):
        return MessageSegment.image(response)

    if base_config.get("enable_md_to_pic"):
        if (
            sum(1 for c in response if "\u4e00" <= c <= "\u9fff")
            >= CHINESE_CHAR_THRESHOLD
        ):
            try:
                image_data = await convert_to_image(response)
                if image_data:
                    return MessageSegment.image(image_data)
            except Exception as e:
                if e.__class__.__name__ != "FinishedException":
                    logger.error(f"Markdown转图片失败: {e}")
                    return f"图片生成失败，已回退到文本显示:\n{response}"

    return response


@ai.handle()
async def chat_handler(
    bot: Bot, event: MessageEvent, result: CommandResult, msg: UniMsg
):
    user_id_str = event.get_user_id()

    try:
        main_args = result.result.main_args if result.result.main_args else {}
        query_segments = main_args.get("query", [])
        query = UniMessage(query_segments).extract_plain_text().strip()
        logger.debug(f"提取的指令文本: '{query}'")

        full_message = UniMessage(query_segments)

        if event.reply and event.reply.message:
            logger.debug("检测到引用消息，正在使用便捷方法转换并合并内容...")
            reply_unimessage = message_to_unimessage(event.reply.message)
            full_message = reply_unimessage + full_message
            logger.debug(f"合并后的完整消息包含 {len(full_message)} 个段。")

            if not query:
                updated_query = full_message.extract_plain_text().strip()
                if updated_query:
                    query = updated_query
                    logger.debug(f"从合并消息中更新查询文本: '{query}'")
        else:
            logger.debug("未检测到引用消息。")

        media_types_to_check = (UniImage, UniVideo, UniVoice)
        has_media = any(full_message.has(t) for t in media_types_to_check)
        if not query and not has_media:
            await ai.finish("请提供问题或附带图片、文件等内容。")
            return

        if has_media:
            active_model_name = get_current_active_model_name()
            if not active_model_name:
                await ai.finish("错误：当前未配置任何AI模型。")
                return

            async with await get_model_instance(active_model_name) as model_instance:
                unsupported_media = []
                if (
                    full_message.has(UniImage)
                    and not model_instance.can_process_images()
                ):
                    unsupported_media.append("图片")
                if (
                    full_message.has(UniVideo)
                    and not model_instance.can_process_video()
                ):
                    unsupported_media.append("视频")
                if (
                    full_message.has(UniVoice)
                    and not model_instance.can_process_audio()
                ):
                    unsupported_media.append("音频")

                if unsupported_media:
                    media_types_str = "、".join(unsupported_media)
                    error_message = (
                        f"当前模型 `{active_model_name}` 不支持处理 {media_types_str} 内容。"
                        f"请切换到支持多模态的模型或发送纯文本。"
                    )
                    logger.warning(
                        f"用户 {user_id_str} 尝试使用不支持的媒体类型 ({media_types_str}) "
                        f"与模型 {active_model_name}."
                    )
                    await ai.finish(error_message)
                    return

        group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None

        session_state = session_manager.get_or_create_session(user_id_str, group_id)

        if session_state.status == SessionStatus.PROCESSING_AGENT:
            await ai.finish("我正在思考中，请稍等片刻再发送消息哦~")
            return

        response: str | bytes
        ai_instance = session_state.ai_instance
        current_intent = session_state.intent

        if (
            session_state.status == SessionStatus.AWAITING_USER_INPUT
            and current_intent in AGENT_CONFIGS
        ):
            logger.info(
                f"🚦 检测到用户正处于 {current_intent} 任务中，继续Agent循环..."
            )
            ai_instance.history.append(
                LLMMessage.user(await unimsg_to_llm_parts(full_message))
            )
            agent_config = AGENT_CONFIGS[current_intent]
            response = await run_generic_agent_loop(
                session_state=session_state,
                mcp_tool_name=agent_config["tool_name"],
                system_prompt=agent_config["system_prompt"],
                bot=bot,
                event=event,
                model_name=base_config.get("AGENT_MODEL_NAME"),
            )
        else:
            if session_state.status != SessionStatus.IDLE:
                logger.warning(
                    f"会话状态为 {session_state.status.value} 但未被处理，重置为IDLE。"
                )
                session_state.status = SessionStatus.IDLE
                session_state.intent = None

            if base_config.get("enable_ai_intent_detection"):
                intent_result = await detect_function_calling_intent_with_ai(query)
            else:
                intent_result = detect_intent_by_keywords(query)

            intent = intent_result.get("intent")
            logger.info(
                f"🧠 意图检测: {intent} (置信度: {intent_result.get('confidence', 1.0):.2f}) "
                f"| AI检测: {'已启用' if base_config.get('enable_ai_intent_detection') else '已禁用'}"
            )

            if (
                intent in AGENT_CONFIGS
                and base_config.get("enable_mcp_tools")
                and MCP_AVAILABLE
            ):
                logger.info(f"🚦 路由到通用 Agent 循环处理: {intent}")
                ai_instance.history.append(
                    LLMMessage.user(await unimsg_to_llm_parts(full_message))
                )
                session_state.intent = intent
                agent_config = AGENT_CONFIGS[intent]
                response = await run_generic_agent_loop(
                    session_state=session_state,
                    mcp_tool_name=agent_config["tool_name"],
                    system_prompt=agent_config["system_prompt"],
                    bot=bot,
                    event=event,
                    model_name=base_config.get("AGENT_MODEL_NAME"),
                )
            elif intent == "SEARCH":
                logger.info("🚦 路由到内置搜索: SEARCH")
                search_instruction = (
                    f"请用中文搜索并详细回答。用户的问题是：'{query}'\n"
                    f"{MARKDOWN_STYLING_PROMPT}"
                )
                search_result = await ai_instance.search(
                    full_message, instruction=search_instruction
                )

                if search_result.get("success", False):
                    response_text = search_result.get("text", "")
                    sources = search_result.get("sources", [])
                    queries = search_result.get("queries", [])

                    if queries:
                        response_text += "\n\n🔍 搜索查询："
                        for i, query_text in enumerate(queries[:3], 1):
                            response_text += f"\n{i}. {query_text}"

                    if sources:
                        response_text += "\n\n📚 信息来源："
                        for i, source in enumerate(sources[:5], 1):
                            title = getattr(source, "title", "未知来源")
                            uri = getattr(source, "uri", "")
                            response_text += f"\n{i}. {title}" + (
                                f" - {uri}" if uri else ""
                            )

                    logger.info(
                        f"✅ 搜索成功，来源数量: {len(sources)}, 查询数量: {len(queries)}"
                    )
                    response = f"🔍 搜索结果：\n{response_text}"
                else:
                    logger.warning("搜索失败，回退到普通分析模式")
                    fallback_prompt = (
                        f"请用中文详细回答关于 '{query}' 的问题。请提供准确、详细的信息。\n"
                        f"{MARKDOWN_STYLING_PROMPT}"
                    )
                    llm_response = await ai_instance.analyze(
                        full_message, instruction=fallback_prompt
                    )
                    response = llm_response.text
            else:
                logger.info("🚦 路由到简单对话: CHAT")

                content_parts = await unimsg_to_llm_parts(full_message)

                if not ai_instance.history:
                    chat_instruction = f"请用中文回复。\n{MARKDOWN_STYLING_PROMPT}"
                    ai_instance.history.append(LLMMessage.system(chat_instruction))

                llm_response_obj = await ai_instance.chat(content_parts or "")
                response = llm_response_obj.text

        final_message_to_send = await _prepare_final_response(response)
        await ai.finish(final_message_to_send)

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理聊天请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai.finish(f"处理请求失败: {friendly_message}")
