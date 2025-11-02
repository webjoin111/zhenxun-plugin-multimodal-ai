from typing import TYPE_CHECKING

from nonebot.matcher import Matcher
from nonebot.params import Depends

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
    get_model_instance,
    message_to_unimessage,
    unimsg_to_llm_parts,
    LLMException,
    LLMGenerationConfig,
    LLMMessage,
)
from zhenxun.services.llm.types import get_user_friendly_error_message
from zhenxun.services.log import logger

from zhenxun import ui
from .. import ai
from ..config import (
    CHINESE_CHAR_THRESHOLD,
    CSS_DIR,
    MARKDOWN_STYLING_PROMPT,
    base_config,
)
from ..core import get_current_active_model_name

from ..core.session_manager import session_manager

from ..core.intent import (
    detect_function_calling_intent_with_ai,
    detect_intent_by_keywords,
)


async def _handle_search_intent(ai_instance, message: UniMessage, query: str) -> str:
    """处理 SEARCH 意图：直接、单次调用 Gemini Grounding。"""
    logger.info("🚦 路由策略: SEARCH (直接调用)")
    search_instruction = (
        f"请用中文搜索并详细回答。用户的问题是：'{query}'\n{MARKDOWN_STYLING_PROMPT}"
    )

    try:
        search_response = await ai_instance.search(
            message, instruction=search_instruction
        )

        response_text = search_response.text

        if search_response.grounding_metadata:
            sources = search_response.grounding_metadata.grounding_attributions or []
            queries = search_response.grounding_metadata.web_search_queries or []

            if sources:
                response_text += "\n\n📚 **参考来源：**\n"
                for i, source in enumerate(sources[:3], 1):
                    title = source.title or "未知标题"
                    url = source.uri or ""
                    if url:
                        response_text += f"{i}. [{title}]({url})\n"
                    else:
                        response_text += f"{i}. {title}\n"

            if queries:
                response_text += f"\n🔍 **搜索查询：** {', '.join(queries)}"

        return f"🔍 搜索结果：\n{response_text}"

    except LLMException as e:
        logger.warning(f"搜索失败: {e.user_friendly_message}", e=e)
        return f"抱歉，搜索功能当前似乎出了点问题：{e.user_friendly_message}"
    except Exception as e:
        logger.error("处理搜索意图时发生未知错误", e=e)
        return "抱歉，搜索功能当前似乎出了点问题，请稍后再试。"


async def _prepare_final_response(response: str | bytes) -> str | MessageSegment:
    """统一处理最终的响应，准备待发送的消息段，包括Markdown转图片逻辑"""
    if isinstance(response, bytes):
        return MessageSegment.image(response)
    assert isinstance(response, str)
    if base_config.get("enable_md_to_pic"):
        if (
            sum(1 for c in response if "\u4e00" <= c <= "\u9fff")  # type: ignore
            >= CHINESE_CHAR_THRESHOLD
        ):
            try:
                theme_name = base_config.get("THEME", "light")
                css_path = CSS_DIR / f"{theme_name}.css"
                md_component = ui.markdown(response)
                md_component.css_path = str(css_path.absolute())
                md_component.component_css = """
                body {
                    padding: 20px;
                    line-height: 1.6;
                }
                """
                image_data = await ui.render(md_component)
                if image_data:
                    return MessageSegment.image(image_data)
            except Exception as e:
                if e.__class__.__name__ != "FinishedException":
                    logger.error(f"Markdown转图片失败: {e}")
                    return f"图片生成失败，已回退到文本显示:\n{response}"

    return response


@ai.handle()
async def chat_handler(
    bot: Bot,
    event: MessageEvent,
    result: CommandResult,
    msg: UniMsg,
    matcher: Matcher = Depends(),
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
        ai_instance = session_state.ai_instance

        if base_config.get("enable_ai_intent_detection"):
            intent_result = await detect_function_calling_intent_with_ai(query)
        else:
            intent_result = detect_intent_by_keywords(query)

        intent = intent_result.get("intent")
        logger.info(f"🧠 意图检测: {intent}")

        generation_config_params = {
            k: v
            for k, v in main_args.items()
            if k in ["temperature", "top_p", "top_k", "max_tokens", "stop_sequences"]
        }

        base_gen_config = (
            LLMGenerationConfig(**generation_config_params)
            if generation_config_params
            else None
        )

        response_text = ""

        user_content_parts = await unimsg_to_llm_parts(full_message)
        current_user_message = LLMMessage.user(user_content_parts or query)

        if intent == "SEARCH":
            response_text = await _handle_search_intent(
                ai_instance, full_message, query
            )
            await ai_instance.add_user_message_to_history(current_user_message)
            await ai_instance.add_assistant_response_to_history(response_text)

        if intent == "CHAT":
            logger.info("🚦 路由策略: CHAT (直接调用 ai.chat)")
            chat_response = await ai_instance.chat(
                current_user_message,
                instruction=MARKDOWN_STYLING_PROMPT,
                **base_gen_config.to_dict() if base_gen_config else {},
            )
            response_text = chat_response.text

        if not response_text:
            response_text = "任务已执行，但AI没有提供额外的文本回复。"

        final_message_to_send = await _prepare_final_response(response_text)
        await ai.finish(final_message_to_send)

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理聊天请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai.finish(f"处理请求失败: {friendly_message}")
