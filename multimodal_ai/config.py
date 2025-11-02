from pathlib import Path

from zhenxun.configs.config import Config

PLUGIN_DIR = Path(__file__).parent

# Markdown转图片相关配置
CHINESE_CHAR_THRESHOLD = 100  # 中文字符阈值，超过此值将转为图片
CSS_DIR = PLUGIN_DIR / "css"  # Markdown转图片的CSS样式文件目录

base_config = Config.get("multimodal_ai")

MARKDOWN_STYLING_PROMPT = """
注意使用丰富的markdown格式让内容更美观，注意要在合适的场景使用合适的样式,不合适就不使用,包括：
标题层级(h1-h6)、粗体(bold)、斜体(em)、引用块(blockquote)、
有序列表(ordered list)、无序列表(unordered list)、任务列表(checkbox)、
代码块(code)、内联代码(inline code)、表格(table)、分隔线(hr)、
删除线(Strikethrough)、链接(links)、嵌套列表(nested lists)、emoji增强格式(emoji-enhanced formatting).
避免使用: Mermaid图表(graph td)。
""".strip()


