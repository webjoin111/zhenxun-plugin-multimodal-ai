from arclet.alconna import (
    Alconna,
    AllParam,
    Args,
    CommandMeta,
    Field,
    Subcommand,
)
from nonebot import get_driver, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, is_type
from nonebot_plugin_alconna import on_alconna
from nonebot_plugin_alconna.uniseg import Image as UniImage
from nonebot_plugin_alconna.uniseg import UniMsg

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.configs.utils import PluginCdBlock, PluginExtraData, RegisterConfig
from zhenxun.services.llm.core import http_client_manager
from zhenxun.services.log import logger
from zhenxun.utils.enum import LimitWatchType, PluginLimitType

from .core import validate_active_model_on_startup
from .core.queue_manager import draw_queue_manager

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

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
        "⚙️ 模型管理：\n"
        "  ai模型 列表 - 查看可用模型\n"
        "  ai模型 切换 [Provider/Model] - 切换对话模型（超级用户）\n\n"
        "🎨 ai绘图/ai绘画：\n"
        "  ai绘图/ai绘画 [描述] - ai图片生成\n"
        "  ai绘图/ai绘画 [描述] [图片] - 基于图片进行风格转换\n"
        "🎨 主题管理：\n"
        "  ai主题 列表 - 查看所有可用的主题\n"
        "  ai主题 切换 [主题名] - 切换Markdown转图片主题（超级用户）\n\n"
        "🖼️ 配置管理：\n"
        "  ai配置 md on/off - 开关Markdown转图片（超级用户）\n"
        "  ai配置 绘图 on/off - 开关AI绘图功能（超级用户）\n\n"
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
        version="1.0",
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
                key="enable_draw_prompt_optimization",
                value=False,
                help="是否启用AI绘图描述优化。开启后会使用辅助LLM润色用户描述以生成更佳效果，会额外消耗API额度。",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="MODEL_NAME",
                value="Gemini/gemini-2.5-flash",
                help="当前激活的模型名称，格式：提供商/模型名",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="AGENT_MODEL_NAME",
                value="Gemini/gemini-2.5-flash-lite-preview-06-17",
                help="用于Agent工具调用功能的模型名称，格式：提供商/模型名",
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
                key="enable_mcp_tools",
                value=False,
                help="是否启用MCP（模型上下文协议）工具，如百度地图。需要额外安装 'mcp' 库。",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="enable_ai_draw",
                value=True,
                help="是否启用AI绘图功能",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="DOUBAO_COOKIES",
                value="",
                help="豆包AI绘图的Cookies，用于免登录生成图片。获取方式请参考插件文档。",
            ),
            RegisterConfig(
                module="multimodal_ai",
                key="HEADLESS_BROWSER",
                value=True,
                help="是否使用无头浏览器模式进行AI绘图。True为后台运行（服务器推荐），False会弹出浏览器窗口（便于本地调试）。",
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
                limit_type=PluginLimitType.CD,
                watch_type=LimitWatchType.USER,
                status=True,
                result="AI功能冷却中，请等待{cd}后再试~",
            )
        ],
    ).dict(),
)

ai_alconna = Alconna(
    "ai",
    Args["query?", AllParam],
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
    Subcommand(
        "绘图",
        Args["action", str],
        alias=["draw"],
        help_text="开关AI绘图功能（仅超级用户）",
    ),
    meta=CommandMeta(
        description="AI配置管理",
        usage="ai配置 <子命令> [参数]",
        example="ai配置 md on\nai配置 绘图 on",
    ),
)


ai_draw_alconna = Alconna(
    ["ai绘图", "ai绘画"],
    Args["prompt?", AllParam, Field(completion=lambda: "输入图片描述...")],
    meta=CommandMeta(
        description="ai图片生成",
        usage="ai绘图/ai绘画 <描述>\nai绘图/ai绘画 <描述> [图片] - 基于图片进行风格转换",
        example=(
            "ai绘图 一只可爱的小猫\nai绘画 夕阳下的海滩\nai绘图 变成动漫风格 [附带图片]"
        ),
        strict=False,
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


ai_draw = on_alconna(
    ai_draw_alconna,
    rule=is_type(GroupMessageEvent, MessageEvent),
    priority=5,
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

        from .core.queue_manager import draw_queue_manager
        from .core.session_manager import session_manager

        draw_queue_manager.start_queue_processor()
        logger.info("绘图队列处理器已启动")

        session_manager.start_cleanup_task()
        logger.info("会话管理器已启动")
    except Exception as e:
        logger.error(f"模型配置验证失败: {e}")


@driver.on_shutdown
async def multimodal_ai_shutdown():
    logger.info("Multimodal AI Plugin: 正在关闭，清理LLM HTTP客户端...")
    await http_client_manager.shutdown()
    logger.info("LLM HTTP客户端清理完成。")

    from .core.queue_manager import draw_queue_manager
    from .core.session_manager import session_manager

    await draw_queue_manager.stop_queue_processor()
    logger.info("绘图队列处理器已停止")

    session_manager.stop_cleanup_task()
    logger.info("会话管理器已停止")


@scheduler.scheduled_job(
    "cron", hour=11, minute=30, id="job_cleanup_multimodal_ai_temp_files"
)
async def cleanup_plugin_temp_files():
    """
    每天11:30清理 multimodal-ai 插件在 TEMP_PATH 中产生的所有超过24小时的临时文件。
    这包括AI绘图、Markdown转图片、上传文件、音频转换等所有缓存。
    """
    from datetime import datetime
    import shutil

    base_temp_dir = TEMP_PATH / "multimodal-ai"
    if not base_temp_dir.exists():
        return

    logger.info(f"开始清理插件临时目录: {base_temp_dir}")
    now = datetime.now().timestamp()
    cleanup_threshold = 86400
    cleaned_files = 0
    cleaned_dirs = 0

    try:
        for file_path in base_temp_dir.rglob("*"):
            if file_path.is_file():
                try:
                    if (now - file_path.stat().st_mtime) > cleanup_threshold:
                        file_path.unlink()
                        cleaned_files += 1
                except Exception as e:
                    logger.warning(f"删除临时文件 {file_path} 失败: {e}")

        for dir_path in sorted(
            list(base_temp_dir.rglob("*")), key=lambda p: len(p.parts), reverse=True
        ):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                try:
                    shutil.rmtree(dir_path)
                    cleaned_dirs += 1
                except Exception as e:
                    logger.warning(f"删除空临时目录 {dir_path} 失败: {e}")

        if cleaned_files > 0 or cleaned_dirs > 0:
            logger.info(
                f"插件临时目录清理完成。删除了 {cleaned_files} 个文件和 {cleaned_dirs} 个空目录。"
            )
        else:
            logger.debug("插件临时目录中没有需要清理的文件或目录。")
    except Exception as e:
        logger.error(f"清理插件临时目录时发生未知错误: {e}")


@scheduler.scheduled_job("cron", hour=2, id="job_clean_queue_requests")
async def clean_old_queue_requests():
    """清理旧的队列请求记录"""
    try:
        await draw_queue_manager.cleanup_old_requests(max_age_hours=24)
    except Exception as e:
        logger.error(f"清理队列请求记录失败: {e}")


from . import handlers  # noqa: F401
