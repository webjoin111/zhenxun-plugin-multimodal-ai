from pathlib import Path

from zhenxun.configs.config import Config

PLUGIN_DIR = Path(__file__).parent

# Markdown转图片相关配置
MD_FONT_SIZE = 14  # Markdown转图片的字体大小（像素）
CHINESE_CHAR_THRESHOLD = 100  # 中文字符阈值，超过此值将转为图片
CSS_DIR = PLUGIN_DIR / "css"  # Markdown转图片的CSS样式文件目录

# 浏览器相关配置
BROWSER_COOLDOWN_SECONDS = 20  # 浏览器关闭后的冷却时间（秒），冷却期间不接受新绘图请求

base_config = Config.get("multimodal_ai")
