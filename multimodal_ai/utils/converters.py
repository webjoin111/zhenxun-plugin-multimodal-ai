import io
from pathlib import Path
import re
import time
import uuid
import wave

import aiofiles
import markdown
from nonebot_plugin_htmlrender import data_source as hr_data
from nonebot_plugin_htmlrender import html_to_pic

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger

from ..config import CSS_DIR, MD_FONT_SIZE, base_config

env = hr_data.env


async def convert_to_image(markdown_text: str) -> bytes | None:
    """将Markdown文本转换为图片"""
    if not html_to_pic or not env:
        logger.error(
            "未安装 nonebot_plugin_htmlrender 或其依赖，无法使用 Markdown 转图片功能"
        )
        return None

    try:
        processed_text = process_markdown(markdown_text)

        html_content = markdown.markdown(
            processed_text,
            extensions=[
                "pymdownx.tasklist",
                "tables",
                "fenced_code",
                "codehilite",
                "mdx_math",
                "pymdownx.tilde",
            ],
            extension_configs={"mdx_math": {"enable_dollar_delimiter": True}},
        )

        theme_name = base_config.get("THEME", "light")
        theme_css_path = CSS_DIR / f"{theme_name}.css"

        if not theme_css_path.exists():
            logger.warning(
                f"主题CSS文件 '{theme_css_path}' 不存在。将回退到默认的 'light' 主题。"
            )
            theme_css_path = CSS_DIR / "light.css"
            if not theme_css_path.exists():
                logger.error(
                    f"致命错误：默认主题文件 '{theme_css_path}' 缺失，无法生成图片。"
                )
                return None

        async with aiofiles.open(theme_css_path, encoding="utf-8") as f:
            css_content = await f.read()
        logger.debug(f"成功加载Markdown主题CSS: {theme_css_path}")

        additional_css = f"""
        body {{
            font-size: {MD_FONT_SIZE}px;
            padding: 20px;
            line-height: 1.6;
        }}
        """
        modified_css = css_content + additional_css

        template = env.get_template("markdown.html")
        extra = ""
        if "math/tex" in html_content:
            katex_css = await hr_data.read_tpl("katex/katex.min.b64_fonts.css")
            katex_js = await hr_data.read_tpl("katex/katex.min.js")
            mhchem_js = await hr_data.read_tpl("katex/mhchem.min.js")
            mathtex_js = await hr_data.read_tpl("katex/mathtex-script-type.min.js")
            extra = (
                f'<style type="text/css">{katex_css}</style>'
                f"<script defer>{katex_js}</script>"
                f"<script defer>{mhchem_js}</script>"
                f"<script defer>{mathtex_js}</script>"
            )

        full_html = await template.render_async(
            md=html_content, css=modified_css, extra=extra
        )

        image_data = await html_to_pic(
            html=full_html,
            template_path=f"file://{hr_data.TEMPLATES_PATH}",
            viewport={"width": 800, "height": 10},
            device_scale_factor=2,
        )

        return image_data
    except Exception as e:
        logger.error(f"Markdown转图片失败: {e}")
        return None


def process_markdown(text: str) -> str:
    """处理Markdown文本，确保格式正确"""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"```(\w*)\s*\n", r"```\1\n", text)
    text = re.sub(r"^(#+)([^\s#])", r"\1 \2", text, flags=re.MULTILINE)
    text = re.sub(r"^([*\-+])([^\s*\-+])", r"\1 \2", text, flags=re.MULTILINE)
    return text


async def save_audio_to_temp_file(
    audio_data: bytes, file_extension: str = "wav"
) -> str:
    """将音频数据保存到临时文件并返回文件路径"""
    try:
        logger.info(f"💾 开始保存音频数据到临时文件，数据大小: {len(audio_data)} 字节")

        is_pcm_data = not (
            audio_data.startswith(b"RIFF") and b"WAVE" in audio_data[:12]
        )

        if is_pcm_data and file_extension.lower() == "wav":
            logger.debug("🔧 检测到PCM数据，转换为WAV格式")
            audio_data = convert_pcm_to_wav(audio_data)
            logger.debug(f"✅ PCM转WAV完成，新数据大小: {len(audio_data)} 字节")

        temp_dir = TEMP_PATH / "multimodal-ai" / "audio"
        temp_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = (
            f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.{file_extension}"
        )
        temp_path = temp_dir / unique_filename

        logger.debug(f"📁 创建临时文件: {temp_path}")

        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(audio_data)

        logger.info(f"✅ 音频数据已保存到临时文件: {temp_path}")

        if Path(temp_path).exists():
            file_size = Path(temp_path).stat().st_size
            logger.debug(f"✅ 文件验证成功，文件大小: {file_size} 字节")
        else:
            logger.error(f"❌ 临时文件创建失败，文件不存在: {temp_path}")
            raise FileNotFoundError(f"临时文件创建失败: {temp_path}")

        return str(temp_path)

    except Exception as e:
        logger.error(f"❌ 保存音频到临时文件失败: {e}")
        logger.error(f"📋 异常类型: {type(e).__name__}")
        raise


def convert_pcm_to_wav(
    pcm_data: bytes, channels: int = 1, sample_rate: int = 24000, sample_width: int = 2
) -> bytes:
    """将PCM数据转换为WAV格式"""
    logger.debug(
        f"🔧 转换PCM到WAV: 声道={channels}, 采样率={sample_rate}, 位宽={sample_width}字节"
    )

    wav_buffer = io.BytesIO()

    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)

    wav_data = wav_buffer.getvalue()
    logger.debug(f"✅ PCM转WAV完成，输出大小: {len(wav_data)} 字节")

    return wav_data


def convert_gif_to_png(gif_data: bytes) -> tuple[bytes, str]:
    """将GIF数据转换为PNG格式"""
    try:
        from PIL import Image

        gif_image = Image.open(io.BytesIO(gif_data))

        if hasattr(gif_image, "is_animated") and gif_image.is_animated:
            gif_image.seek(0)
            logger.debug("检测到动画GIF，将使用第一帧进行转换")

        if gif_image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", gif_image.size, (255, 255, 255))
            if gif_image.mode == "RGBA":
                background.paste(gif_image, mask=gif_image.split()[-1])
            else:
                background.paste(gif_image, mask=gif_image.split()[-1])
            gif_image = background
        elif gif_image.mode != "RGB":
            gif_image = gif_image.convert("RGB")

        png_buffer = io.BytesIO()
        gif_image.save(png_buffer, format="PNG", optimize=True)
        png_data = png_buffer.getvalue()

        logger.debug(f"GIF转PNG成功: {len(gif_data)} bytes -> {len(png_data)} bytes")
        return png_data, "image/png"

    except Exception as e:
        logger.error(f"GIF转PNG失败: {e}")
        raise ValueError(f"GIF格式转换失败: {e}")
