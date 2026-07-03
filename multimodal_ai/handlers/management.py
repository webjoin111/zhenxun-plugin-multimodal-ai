from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import CommandResult

from zhenxun.configs.config import Config
from zhenxun.services.ai.core.exceptions import get_user_friendly_error_message
from zhenxun.services.log import logger

from .. import ai_config, ai_theme
from ..config import CSS_DIR, base_config


def _list_available_themes() -> list[str]:
    """扫描CSS目录并返回所有可用的主题名称。"""
    if not CSS_DIR.exists() or not CSS_DIR.is_dir():
        return []

    themes = sorted({p.stem for p in CSS_DIR.glob("*.css") if p.is_file()})
    return themes


@ai_config.handle()
async def handle_ai_config(bot: Bot, event: MessageEvent, result: CommandResult):
    try:
        if not await SUPERUSER(bot, event):
            await ai_config.finish("仅超级管理员可修改此设置")

        subcommands = result.result.subcommands if result.result.subcommands else {}

        if subcommands.get("md"):
            action = subcommands["md"].args.get("action", "").lower()
            if action in ["on", "enable"]:
                Config.set_config(
                    "multimodal_ai", "enable_md_to_pic", True, auto_save=True
                )
                await ai_config.finish("已启用Markdown转图片功能")
            elif action in ["off", "disable"]:
                Config.set_config(
                    "multimodal_ai", "enable_md_to_pic", False, auto_save=True
                )
                await ai_config.finish("已禁用Markdown转图片功能")
            else:
                await ai_config.finish(
                    f"当前Markdown转图片状态：{'已启用' if base_config.get('enable_md_to_pic') else '已禁用'}\n"
                    f"使用 'ai配置 md on/off' 来切换状态"
                )

        elif (subcommand_key := next((k for k in ("绘图", "draw") if subcommands.get(k)), None)):
            action = subcommands[subcommand_key].args.get("action", "").lower()
            if action in ["on", "enable"]:
                Config.set_config(
                    "multimodal_ai", "enable_ai_draw", True, auto_save=True
                )
                await ai_config.finish("已启用AI绘图功能")
            elif action in ["off", "disable"]:
                Config.set_config(
                    "multimodal_ai", "enable_ai_draw", False, auto_save=True
                )
                await ai_config.finish("已禁用AI绘图功能")
            else:
                await ai_config.finish(
                    f"当前 AI 绘图 (draw) 状态：{'已启用' if base_config.get('enable_ai_draw') else '已禁用'}\n"
                    f"使用 'ai配置 draw on/off' 来切换状态"
                )

        else:
            await ai_config.finish(
                "AI配置管理命令：\n"
                "- ai配置 md on/off：开关Markdown转图片功能\n"
                "- ai配置 draw on/off：开关AI绘图功能"
            )

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理AI配置请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai_config.finish(f"处理请求失败: {friendly_message}")





@ai_theme.handle()
async def theme_management_handler(
    bot: Bot, event: MessageEvent, result: CommandResult
):
    """处理AI主题的查看和切换命令。"""
    try:
        subcommands = result.result.subcommands if result.result.subcommands else {}
        available_themes = _list_available_themes()

        if subcommands.get("列表") or subcommands.get("list"):
            if not available_themes:
                await ai_theme.finish("❌ 未找到任何可用主题。")
                return

            current_theme = base_config.get("THEME", "light")

            message = "🎨 可用主题列表：\n"
            for theme in available_themes:
                if theme == current_theme:
                    message += f"  - {theme} **[当前使用]**\n"
                else:
                    message += f"  - {theme}\n"

            message += "\n💡 使用 `ai主题 切换 <主题名>` 来切换主题。"
            await ai_theme.finish(message.strip())

        elif subcommands.get("切换") or subcommands.get("switch"):
            if not await SUPERUSER(bot, event):
                await ai_theme.finish("❌ 权限不足，仅超级用户可以切换主题。")
                return

            subcommand_key = "切换" if subcommands.get("切换") else "switch"
            theme_name = subcommands[subcommand_key].args.get("theme_name")

            if not theme_name:
                await ai_theme.finish("请提供要切换的主题名称。")
                return

            if theme_name in available_themes:
                Config.set_config("multimodal_ai", "THEME", theme_name, auto_save=True)
                logger.info(
                    f"AI主题已由用户 {event.get_user_id()} 切换为: {theme_name}"
                )
                await ai_theme.finish(f"✅ 主题已成功切换为: **{theme_name}**")
            else:
                await ai_theme.finish(
                    f"❌ 未找到主题 '{theme_name}'。\n"
                    f"可用主题有: {', '.join(available_themes)}"
                )

        else:
            await ai_theme.finish(
                "AI主题管理命令：\n"
                "- `ai主题 列表`：查看所有可用的主题\n"
                "- `ai主题 切换 <主题名称>`：切换主题（仅超级用户）"
            )

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理主题管理请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai_theme.finish(f"处理请求失败: {friendly_message}")
