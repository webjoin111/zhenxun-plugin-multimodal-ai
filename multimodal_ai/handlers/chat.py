from typing import Any, TYPE_CHECKING

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

from zhenxun.services.ai.flow.agent import Agent
from zhenxun.services.ai.context.memory.builder import MemoryBuilder
from zhenxun.services.ai.run.context import RunContext, NoneBotDeps
from zhenxun.services.ai.tools.providers.mcp import MCPSource
from zhenxun.services.ai.tools.providers.builtin.native import WebSearchTool
from zhenxun.services.ai.core.exceptions import get_user_friendly_error_message
from zhenxun.services.log import logger

from zhenxun import ui
from .. import ai
from ..config import (
    CHINESE_CHAR_THRESHOLD,
    CSS_DIR,
    MARKDOWN_STYLING_PROMPT,
    base_config,
)


from ..core import session_manager


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

        media_types_to_check = (UniImage, UniVideo, UniVoice)
        has_media = any(full_message.has(t) for t in media_types_to_check)
        if not query and not has_media:
            await ai.finish("请提供问题或附带图片、文件等内容。")
            return

        group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None

        session_id = await session_manager.touch_session(user_id_str, group_id)

        tools: list[Any] = []
        
        if base_config.get("enable_web_search", False):
            tools.append(WebSearchTool())
        if base_config.get("enable_mcp_tools", False):
            tools.append(MCPSource.all_enabled())

        memory_builder = MemoryBuilder.auto().with_multimodal_window(5)
        if base_config.get("context_timeout_minutes") <= 0:
            memory_builder.with_short_term(enable=False)

        agent = Agent(
            name="MultimodalAI",
            instruction=MARKDOWN_STYLING_PROMPT,
            model=base_config.get("MODEL_NAME"),
            tools=tools,
            memory=memory_builder,
        )

        context = RunContext(
            session_id=session_id, deps=NoneBotDeps(bot=bot, event=event)
        )

        agent_result = await agent.run(prompt=full_message, context=context)
        response_text = str(agent_result.output)

        if not response_text:
            response_text = "任务已执行，但AI没有提供额外的文本回复。"

        final_message_to_send = await _prepare_final_response(response_text)
        await ai.finish(final_message_to_send)

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理聊天请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai.finish(f"处理请求失败: {friendly_message}")
