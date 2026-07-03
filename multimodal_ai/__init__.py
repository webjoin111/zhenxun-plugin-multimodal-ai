from arclet.alconna import (
    Alconna,
    Args,
    CommandMeta,
    MultiVar,
    Subcommand,
)
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, is_type
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMsg

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services.log import logger

__plugin_meta__ = PluginMetadata(
    name="多模态AI助手",
    description="多模态AI助手，支持多种AI模型，支持图片、视频、音频、文档等多种格式的交互",
    usage=(
        "基于Zhenxun LLM服务的多模态AI助手，支持智能对话和文件分析\n\n"
        "🤖 基础对话：\n"
        "  .ai [问题] - 智能对话\n\n"
        "📁 多模态分析：\n"
        "  [引用包含文件的消息] + .ai [问题] - 分析引用消息中的文件\n"
        "  支持格式：图片、音频、视频、文档等\n\n"
        "🎨 主题管理：\n"
        "  ai主题 列表 - 查看所有可用的主题\n"
        "  ai主题 切换 [主题名] - 切换Markdown转图片主题（超级用户）\n\n"
        "🖼️ 配置管理：\n"
        "  ai配置 md on/off - 开关Markdown转图片（超级用户）\n\n"
    ),
    type="application",
    homepage="https://github.com/webjoin111/zhenxun-plugin-multimodal-ai",
    supported_adapters={"~onebot.v11"},
    extra=PluginExtraData(
        author="webjoin111",
        version="1.0.5",
        configs=[
            RegisterConfig(
                module="multimodal_ai",
                key="enable_md_to_pic",
                value=True,
                help="是否启用Markdown转图片功能",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="enable_web_search",
                value=False,
                help="是否启用内置的网页搜索工具，开启后大模型可以自主联网搜索信息(只有gemini模型和openai_response协议的gpt模型支持)",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="THEME",
                value="light",
                help="Markdown转图片使用的主题（对应css目录下无需后缀的文件名，例如 light, dark）",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="MODEL_NAME",
                value="Gemini/gemini-2.5-flash",
                help="当前激活的模型名称，格式：提供商/模型名",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="enable_mcp_tools",
                value=False,
                help="是否挂载全局开启的 MCP 工具。开启后 Agent 可以自动调用外部系统工具（如查天气等）。",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="context_timeout_minutes",
                value=5,
                help="会话上下文超时时间（分钟），设置为0则关闭上下文对话功能",
            ),
        ],
    ).dict(),
)

ai_alconna = Alconna(
    ["."],
    "ai",
    Args["query?", MultiVar(str | UniImage)],
    meta=CommandMeta(
        description="多模态AI助手",
        usage=".ai [问题] - 智能对话和多模态分析\n.ai [问题] + 图片 - 图片分析",
        example=".ai 你好\n.ai 搜索天气\n.ai 分析这张图片 [图片]",
        strict=False,
    ),
)


async def ai_command_rule(event: MessageEvent, msg: UniMsg) -> bool:
    """自定义规则：过滤单独的'.ai'命令，除非有引用消息或图片"""
    message_text = msg.extract_plain_text().strip()

    if not message_text.lower().startswith(".ai"):
        return True

    if message_text.lower() == ".ai":
        has_images = bool(msg[UniImage])
        has_reply_content = bool(event.reply and event.reply.message)

        if not has_images and not has_reply_content:
            logger.debug("单独的'.ai'命令被规则过滤：没有图片或引用消息")
            return False

    return True


ai_config_alconna = Alconna(
    "ai配置",
    Subcommand(
        "md",
        Args["action", str],
        help_text="开关Markdown转图片功能（仅超级用户）",
    ),
    meta=CommandMeta(
        description="AI配置管理",
        usage="ai配置 <子命令> [参数]",
        example="ai配置 md on",
    ),
)


ai_theme_alconna = Alconna(
    "ai主题",
    Subcommand(
        "列表",
        alias=["list"],
        help_text="查看所有可用的主题",
    ),
    Subcommand(
        "切换",
        Args["theme_name", str],
        alias=["switch"],
        help_text="切换Markdown转图片使用的主题（仅超级用户）",
    ),
    meta=CommandMeta(
        description="AI主题管理",
        usage="ai主题 <子命令> [参数]",
        example=("ai主题 列表\nai主题 切换 dark"),
    ),
)


ai = on_alconna(
    ai_alconna,
    rule=is_type(GroupMessageEvent, MessageEvent) & Rule(ai_command_rule),
    priority=5,
    block=True,
    use_origin=False,
)


ai_config = on_alconna(
    ai_config_alconna,
    rule=is_type(GroupMessageEvent, MessageEvent),
    priority=1,
    block=True,
)


ai_theme = on_alconna(
    ai_theme_alconna,
    rule=is_type(GroupMessageEvent, MessageEvent),
    priority=1,
    block=True,
)


from . import handlers  # noqa: E402, F401
