"""
模型管理模块 - 处理模型验证、切换和列表功能
"""

from zhenxun.configs.config import Config
from zhenxun.services.llm import (
    get_global_default_model_name,
    list_available_models,
    set_global_default_model_name,
)
from zhenxun.services.llm.types import get_user_friendly_error_message
from zhenxun.services.log import logger

from ..config import base_config


def get_current_active_model_name() -> str | None:
    """获取当前配置的激活模型名称"""
    return get_global_default_model_name()


def validate_active_model_on_startup():
    """在启动时验证并设置当前激活的模型名称配置"""
    try:
        available_models = list_available_models()
        if available_models:
            model_names = [model["full_name"] for model in available_models]

            if (
                base_config.get("MODEL_NAME")
                and base_config.get("MODEL_NAME") in model_names
            ):
                set_global_default_model_name(base_config.get("MODEL_NAME"))
                logger.info(f"✅ 使用配置的激活模型: {base_config.get('MODEL_NAME')}")
            else:
                first_model = available_models[0]["full_name"]
                set_global_default_model_name(first_model)
                Config.set_config(
                    "multimodal_ai", "MODEL_NAME", first_model, auto_save=True
                )
                logger.info(f"⚠️ 配置的模型不可用，使用第一个可用模型: {first_model}")

            logger.info(f"🎯 最终使用模型: {get_global_default_model_name()}")
        else:
            logger.error("❌ 未找到任何可用模型，请检查LLM服务配置")
    except Exception as e:
        logger.error(f"❌ 模型验证失败: {e}")


def handle_list_models() -> str:
    """获取所有可用模型列表的文本描述"""
    try:
        available_models = list_available_models()
        current_model = get_global_default_model_name()

        if not available_models:
            return "尚未配置任何 AI 模型。请检查 LLM 服务配置。"

        message = "🤖 可用 AI 模型列表：\n"
        message += f"📌 当前使用模型: `{current_model}`\n"
        message += f"📌 插件配置模型: `{base_config.get('MODEL_NAME')}`\n\n"

        for model in available_models:
            full_name = model["full_name"]
            message += f"  - `{full_name}`"

            if full_name == current_model:
                message += " **[当前使用]**"

            capabilities = model.get("capabilities", {})
            if capabilities:
                cap_list = []
                if capabilities.get("supports_function_calling"):
                    cap_list.append("工具调用")
                if capabilities.get("multimodal_capabilities"):
                    cap_list.append("多模态")
                if capabilities.get("supports_streaming"):
                    cap_list.append("流式输出")

                if cap_list:
                    message += f" ({', '.join(cap_list)})"

            message += "\n"

        message += (
            "\n💡 使用 `ai模型 切换 [模型名称]` 来切换当前激活模型 (仅限超级用户)。"
        )
        return message.strip()
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return f"获取模型列表失败: {get_user_friendly_error_message(e)}"


def handle_switch_model(model_name_input: str) -> tuple[bool, str]:
    """切换当前使用的模型"""
    try:
        available_models = list_available_models()
        model_names = [model["full_name"] for model in available_models]

        if model_name_input in model_names:
            set_global_default_model_name(model_name_input)

            Config.set_config(
                "multimodal_ai",
                "MODEL_NAME",
                model_name_input,
                auto_save=True,
            )

            logger.info(f"当前激活模型已切换为: {model_name_input}")
            logger.info(f"已更新插件配置 MODEL_NAME: {model_name_input}")
            return True, f"已切换到模型: {model_name_input}"
        else:
            return (
                False,
                f"错误：未找到模型 '{model_name_input}'。\n可用模型有: {', '.join(model_names)}",
            )
    except Exception as e:
        logger.error(f"切换模型失败: {e}")
        return False, f"切换模型失败: {get_user_friendly_error_message(e)}"
