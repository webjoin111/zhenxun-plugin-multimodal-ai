import json
from pathlib import Path
import re
import tempfile
import time

import aiofiles
import httpx
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import CommandResult, UniMessage, UniMsg
from nonebot_plugin_alconna.uniseg import Image as UniImage

from zhenxun.services.llm import (
    CommonOverrides,
    LLMMessage,
    generate,
    message_to_unimessage,
    unimsg_to_llm_parts,
)
from zhenxun.services.llm.config import LLMGenerationConfig
from zhenxun.services.llm.types import get_user_friendly_error_message
from zhenxun.services.log import logger

from .. import ai_draw
from ..config import base_config
from ..core.queue_manager import draw_queue_manager


async def send_images_as_forward(
    bot: Bot, event: MessageEvent, images: list, prompt: str
):
    """发送图片作为合并转发消息"""
    try:
        forward_messages = []

        forward_messages.append(
            {
                "type": "node",
                "data": {
                    "name": "AI绘图助手",
                    "uin": str(bot.self_id),
                    "content": [MessageSegment.text(f"📝 {prompt}")],
                },
            }
        )

        for i, image in enumerate(images):
            content = [
                MessageSegment.text(f"🎨 图片 {i + 1}/{len(images)}"),
                MessageSegment.image(file=image["local_path"]),
            ]

            forward_messages.append(
                {
                    "type": "node",
                    "data": {
                        "name": "AI绘图助手",
                        "uin": str(bot.self_id),
                        "content": content,
                    },
                }
            )

        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_messages,
            )
            logger.info(f"✅ 成功发送 {len(images)} 张图片的群聊合并转发消息")
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_messages,
            )
            logger.info(f"✅ 成功发送 {len(images)} 张图片的私聊合并转发消息")

        return True

    except Exception as e:
        logger.error(f"发送合并转发消息失败: {e}")
        return False


async def send_images_as_single_message(
    bot: Bot, event: MessageEvent, images: list, prompt: str
):
    """将所有内容放在一个消息里发送"""
    try:
        message_segments = [MessageSegment.text(f"📝 {prompt}")]

        for i, image in enumerate(images):
            message_segments.append(
                MessageSegment.text(f"\n🎨 图片 {i + 1}/{len(images)}")
            )
            message_segments.append(MessageSegment.image(file=image["local_path"]))

        await bot.send(event, message_segments)
        logger.info(f"✅ 成功发送包含 {len(images)} 张图片的单条消息")
        return True

    except Exception as e:
        logger.error(f"发送单条消息失败: {e}")
        return False


async def _optimize_draw_prompt(user_message: UniMessage, user_id: str) -> str:
    """
    使用支持视觉功能的LLM优化用户的绘图描述。
    支持“文生图”的创意扩展和“图生图”的指令理解与融合。
    """
    original_prompt = user_message.extract_plain_text().strip()
    logger.info(f"🎨 启用绘图描述优化，正在为用户 '{user_id}' 的描述进行润色...")

    system_prompt = """你是AI绘画提示词工程师。任务：将用户输入转化为详细的AI绘画提示词。

核心规则：润色时不丢失用户原文任何细节。

【场景一：纯文本输入】
扩展简短描述为完整场景，补充：主体特征、动作姿态、环境背景、光线效果、构图视角、艺术风格、画质要求。

示例：
- 输入："一只猫" 
- 输出："特写镜头，一只英国短毛猫，午后阳光下趴在木质窗台打盹，毛发细节清晰，光影柔和，照片级真实感，4k画质"

【场景二：图片+文本输入】
图片为主体，文本为修改指令。只修改文本明确提到的部分，其他元素保持原样。

工作流程：
1. **分析原图**：详细描述主体、姿态、构图、环境、光照、色彩、风格
2. **解析指令**：提取具体修改要求
3. **重构提示词**：保留未提及元素，精确应用修改指令，添加画质词

示例：
- 输入：[黑发女孩公园长椅微笑图] + "换成夜晚东京街头背景"
- 输出："黑发女孩，白色连衣裙，长椅坐姿微笑表情保持不变，背景替换为夜晚东京街头，霓虹灯闪烁，车水马龙，光影斑驳，电影感，4k画质"

【特殊指令】
数量词（"四张图"、"两个版本"）和变化词（"不同的"、"多种"）需保留在提示词开头。

【输出格式】
严格JSON格式，使用中文：
{
    "success": true,
    "original_prompt": "用户原始文本",
    "analysis": "意图分析",
    "optimized_prompt": "优化后的完整提示词"
}
"""

    try:
        logger.debug(
            f"绘图描述优化将使用模型: {base_config.get('auxiliary_llm_model')}"
        )

        gen_config = None
        if "gemini" in base_config.get("auxiliary_llm_model").lower():
            gen_config = CommonOverrides.gemini_json()
        else:
            gen_config = LLMGenerationConfig(response_format={"type": "json_object"})

        content_parts = await unimsg_to_llm_parts(user_message)
        if not content_parts:
            logger.warning("无法从用户消息中提取有效内容进行优化，将使用原始描述。")
            return original_prompt

        messages = [
            LLMMessage.system(system_prompt),
            LLMMessage.user(content_parts),
        ]

        llm_response = await generate(
            messages,
            model=base_config.get("auxiliary_llm_model"),
            **gen_config.to_dict(),
        )
        response_text = llm_response.text

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning("描述优化LLM未返回有效的JSON结构，将使用原始描述。")
            return original_prompt

        parsed_json = json.loads(json_match.group())

        if parsed_json.get("success") and (
            optimized := parsed_json.get("optimized_prompt")
        ):
            logger.info(f"✅ 描述优化成功。优化后: '{optimized}'")
            return optimized
        else:
            logger.warning("描述优化LLM返回内容不符合预期，将使用原始描述。")
            return original_prompt

    except Exception as e:
        logger.error(f"❌ 绘图描述优化失败，将使用原始描述。错误: {e}")
        return original_prompt


@ai_draw.handle()
async def ai_draw_handler(
    bot: Bot, event: MessageEvent, result: CommandResult, msg: UniMsg
):
    """ai绘图命令处理器"""
    user_id_str = event.get_user_id()
    is_superuser = await SUPERUSER(bot, event)

    if not is_superuser:
        if not base_config.get("enable_ai_draw"):
            logger.info(f"用户 {user_id_str} 尝试使用ai绘图，但功能已被管理员禁用")
            return

    try:
        current_text = ""
        replied_text = ""
        full_message_for_media = msg

        raw_text = msg.extract_plain_text().strip()
        if raw_text.startswith("ai绘图"):
            current_text = raw_text[4:].strip()
        elif raw_text.startswith("ai绘画"):
            current_text = raw_text[4:].strip()

        if event.reply and event.reply.message:
            reply_unimsg = message_to_unimessage(event.reply.message)
            replied_text = reply_unimsg.extract_plain_text().strip()
            full_message_for_media = msg + reply_unimsg
            logger.debug("已合并引用消息的媒体内容。")

        prompt_parts = []
        if current_text:
            prompt_parts.append(current_text)
        if replied_text:
            prompt_parts.append(replied_text)
        prompt = ",".join(prompt_parts)

        image_file_path = None
        if image_segments := full_message_for_media[UniImage]:
            first_image = image_segments[0]
            logger.info("检测到图片输入，准备用于绘图...")
            image_data = None
            if first_image.raw:
                image_data = first_image.raw
            elif first_image.path:
                async with aiofiles.open(first_image.path, "rb") as f:
                    image_data = await f.read()
            elif first_image.url:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(first_image.url)
                    resp.raise_for_status()
                    image_data = resp.content

            if image_data:
                temp_dir = Path(tempfile.gettempdir()) / "multimodal_ai" / "temp_images"
                temp_dir.mkdir(parents=True, exist_ok=True)
                timestamp = int(time.time() * 1000)
                temp_filename = f"upload_{timestamp}.png"
                image_file_path = temp_dir / temp_filename

                async with aiofiles.open(image_file_path, "wb") as f:
                    await f.write(image_data)

                logger.info(f"图片已保存到临时文件: {image_file_path}")

        if not prompt and not image_file_path:
            await ai_draw.finish(
                "请提供图片描述或附带图片，例如：ai绘图 一只可爱的小猫"
            )
            return

        optimizer_input_message = UniMessage.text(prompt)
        if image_file_path:
            optimizer_input_message.append(UniImage(path=image_file_path))

        if base_config.get("enable_draw_prompt_optimization"):
            final_prompt_or_list = await _optimize_draw_prompt(
                user_message=optimizer_input_message,
                user_id=user_id_str,
            )
        else:
            final_prompt_or_list = prompt

        if isinstance(final_prompt_or_list, list):
            logger.info(
                f"优化后的描述是一个包含 {len(final_prompt_or_list)} 部分的列表，将合并为单个提示词。"
            )
            final_prompt = " ".join(map(str, final_prompt_or_list))
        else:
            final_prompt = str(final_prompt_or_list)

        logger.info(f"用户 {user_id_str} 请求ai绘图: {final_prompt[:100]}...")
        if image_file_path:
            logger.info(f"包含图片文件: {image_file_path}")

        request = await draw_queue_manager.add_request(
            user_id_str, final_prompt, str(image_file_path) if image_file_path else None
        )

        queue_position = request.queue_position
        is_browser_cooling = draw_queue_manager.is_browser_in_cooldown()

        if (queue_position and queue_position > 1) or is_browser_cooling:
            message = (
                f"📋 您的请求已加入队列\n"
                f"🔢 队列位置: {queue_position}\n"
                f"⏱️ 预估等待: {request.estimated_wait_time:.1f}秒"
            )

            if is_browser_cooling:
                cooldown_remaining = draw_queue_manager.get_browser_cooldown_remaining()
                message += f"\n🔄 浏览器冷却中，剩余: {cooldown_remaining:.1f}秒"

            message += "\n🎨 请耐心等待..."
            await ai_draw.send(message)
        else:
            await ai_draw.send("🎨 正在生成图片，请稍候...")

        draw_queue_manager.start_queue_processor()

        completed_request = await draw_queue_manager.wait_for_request_completion(
            request.request_id,
            timeout=600.0,
        )

        if not completed_request:
            await ai_draw.finish("❌ 请求处理超时，请稍后重试")
            return

        result_data = completed_request.result
        if not result_data:
            error_msg = completed_request.error or "未知错误"
            await ai_draw.finish(f"❌ 图片生成失败: {error_msg}")
            return

        if result_data["success"]:
            images = result_data["images"]
            if images:
                if len(images) == 1:
                    await ai_draw.finish(
                        MessageSegment.image(file=images[0]["local_path"])
                    )
                else:
                    success = await send_images_as_forward(
                        bot, event, images, final_prompt
                    )
                    if not success:
                        logger.warning("合并转发失败，回退到单条消息发送")
                        await send_images_as_single_message(
                            bot, event, images, final_prompt
                        )

                    await ai_draw.finish()
            else:
                await ai_draw.finish("❌ 图片生成失败：未获取到图片数据")
        else:
            error_msg = result_data.get("error", "未知错误")
            logger.error(f"图片生成失败: {error_msg}")
            await ai_draw.finish(f"❌ 图片生成失败: {error_msg}")

        if image_file_path and image_file_path.exists():
            try:
                Path(image_file_path).unlink()
                logger.debug(f"已清理临时图片文件: {image_file_path}")
            except Exception as e:
                logger.warning(f"清理临时图片文件失败: {e}")

    except Exception as e:
        if e.__class__.__name__ != "FinishedException":
            logger.error(f"处理ai绘图请求失败: {e}")
            friendly_message = get_user_friendly_error_message(e)
            await ai_draw.finish(f"ai绘图失败: {friendly_message}")
