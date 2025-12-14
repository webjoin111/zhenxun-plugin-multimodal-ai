from arclet.alconna import (
    Alconna,
    Args,
    CommandMeta,
    Subcommand,
    MultiVar,
)
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, is_type
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMsg
from zhenxun.configs.utils import PluginCdBlock, PluginExtraData, RegisterConfig
from zhenxun.services.llm import AIConfig
from zhenxun.services.log import logger
from zhenxun.utils.enum import LimitWatchType, PluginLimitType

from .core import validate_active_model_on_startup

original_aiconfig_init = AIConfig.__init__

__plugin_meta__ = PluginMetadata(
    name="多模态AI助手",
    description="多模态AI助手，支持多种AI模型，支持图片、视频、音频、文档等多种格式的交互",
    usage=(
        "基于Zhenxun LLM服务的多模态AI助手，支持智能对话和文件分析\n\n"
        "🤖 基础对话：\n"
        "  ai [问题] - 智能对话\n"
        "  ai 搜索[关键词] - 搜索并回答\n\n"
        "📁 多模态分析：\n"
        "  [引用包含文件的消息] + ai [问题] - 分析引用消息中的文件\n"
        "  [直接发送文件] + ai [问题] - 分析当前消息中的文件\n"
        "  支持格式：图片、音频、视频、文档等\n\n"
        "⚙️ 模型/主题管理：\n"
        "  ai模型 列表/切换 - 查看/切换对话模型（超级用户）\n"
        "🎨 主题管理：\n"
        "  ai主题 列表 - 查看所有可用的主题\n"
        "  ai主题 切换 [主题名] - 切换Markdown转图片主题（超级用户）\n\n"
        "🖼️ 配置管理：\n"
        "  ai配置 md on/off - 开关Markdown转图片（超级用户）\n\n"
        "特性：\n"
        "- 智能文件类型识别和处理\n"
        "- 多模态内容综合分析\n"
        "- 统一的AI模型管理\n"
        "- 自动图片输出优化\n"
        "- 上下文连续对话（默认5分钟会话保持）\n"
    ),
    type="application",
    homepage="https://github.com/webjoin111/zhenxun-plugin-multimodal-ai",
    supported_adapters={"~onebot.v11"},
    extra=PluginExtraData(
        author="webjoin111",
        version="1.0.3",
        configs=[
            RegisterConfig(
                module="multimodal_ai",
                key="enable_md_to_pic",
                value=True,
                help="是否启用Markdown转图片功能",
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
                key="enable_ai_intent_detection",
                value=False,
                help="是否启用AI进行意图识别。关闭时，将使用关键词匹配（性能更高，但不够智能）。",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="auxiliary_llm_model",
                value="Gemini/gemini-2.5-flash-lite-preview-06-17",
                help="辅助LLM模型名称，用于意图检测等辅助功能，格式：提供商/模型名",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="context_timeout_minutes",
                value=5,
                help="会话上下文超时时间（分钟），设置为0则关闭上下文对话功能",
            ),
        ],
        limits=[
            PluginCdBlock(
                cd=60,
                limit_type=PluginLimitType.CD,  # type: ignore
                watch_type=LimitWatchType.USER,
                status=True,
                result="AI功能冷却中，请等待{cd}后再试~",
            )
        ],
    ).dict(),
)

ai_alconna = Alconna(
    "ai",
    Args["query?", MultiVar(str | UniImage)],
    meta=CommandMeta(
        description="多模态AI助手",
        usage="ai [问题] - 智能对话和多模态分析\nai [问题] + 图片 - 图片分析",
        example="ai 你好\nai 搜索天气\nai 分析这张图片 [图片]\nai 识图 [图片]",
        strict=False,
    ),
)


async def ai_command_rule(event: MessageEvent, msg: UniMsg) -> bool:
    """自定义规则：过滤单独的'ai'命令，除非有引用消息或图片"""
    message_text = msg.extract_plain_text().strip()

    if not message_text.lower().startswith("ai"):
        return True

    if message_text.lower() == "ai":
        has_images = bool(msg[UniImage])
        has_reply_content = bool(event.reply and event.reply.message)

        if not has_images and not has_reply_content:
            logger.debug("单独的'ai'命令被规则过滤：没有图片或引用消息")
            return False

    return True


ai_model_alconna = Alconna(
    "ai模型",
    Subcommand(
        "列表",
        alias=["list"],
        help_text="查看所有可用的模型",
    ),
    Subcommand(
        "切换",
        Args["model_name", str],
        alias=["switch"],
        help_text="切换对话模型（仅超级用户）",
    ),
    meta=CommandMeta(
        description="AI模型管理",
        usage="ai模型 <子命令> [参数]",
        example=("ai模型 列表\nai模型 切换 Gemini/gemini-2.0-flash"),
    ),
)

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


ai_model = on_alconna(
    ai_model_alconna,
    rule=is_type(GroupMessageEvent, MessageEvent),
    priority=5,
    block=True,
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


driver = get_driver()


@driver.on_startup
async def _():
    logger.info("Multimodal AI Plugin: 正在初始化...")
    try:
        validate_active_model_on_startup()
        logger.info("模型配置验证成功")

        from .config import base_config  # noqa: F401

        from .core.session_manager import session_manager

        session_manager.start_cleanup_task()
        logger.info("会话管理器已启动")
    except Exception as e:
        logger.error(f"模型配置验证失败: {e}")


@driver.on_shutdown
async def multimodal_ai_shutdown():
    logger.info("Multimodal AI Plugin: 正在关闭...")

    from .core.session_manager import session_manager

    session_manager.stop_cleanup_task()
    logger.info("会话管理器已停止")


from . import handlers  # noqa: E402, F401
