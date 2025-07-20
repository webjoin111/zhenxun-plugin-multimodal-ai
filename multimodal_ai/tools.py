import base64
from contextlib import asynccontextmanager
from typing import Any
from .config import base_config
from zhenxun.services.log import logger

try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.types import Tool as MCPTool

    MCP_AVAILABLE = True
except ImportError:
    logger.warning("依赖 'mcp' 未安装，MCP相关工具（如百度地图）将不可用。")
    logger.warning("请运行 'pip install mcp' 来安装。")
    MCP_AVAILABLE = False

    class ClientSession:
        pass

    class StdioServerParameters:
        pass

    class MCPTool:
        pass

    def stdio_client(*args, **kwargs):
        @asynccontextmanager
        async def dummy_context():
            yield None, None

        return dummy_context()


from pydantic import BaseModel, Field

from zhenxun.services.llm.tools import tool_registry
from zhenxun.services.llm.types.protocols import MCPCompatible
from zhenxun.services.log import logger


class MCPClientSessionWrapper(MCPCompatible):
    """
    一个包装器，用于将 mcp.client.session.ClientSession
    适配到 zhenxun.llm 的 MCPCompatible 协议。
    它在进入上下文时预加载工具定义。
    """

    def __init__(self, session: ClientSession):
        self.session = session
        self._tool_definitions: list[dict] | None = None

    async def __aenter__(self):
        """预加载工具定义。"""
        logger.debug("MCP Wrapper: Preloading tool definitions for session...")

        all_mcp_tools: list[MCPTool] = []
        cursor = None
        while True:
            result = await self.session.list_tools(cursor=cursor)
            all_mcp_tools.extend(result.tools)
            if not result.nextCursor:
                break
            cursor = result.nextCursor

        self._tool_definitions = []
        for tool in all_mcp_tools:
            parameters = tool.inputSchema or {"type": "object", "properties": {}}
            self._tool_definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                }
            )

        logger.debug(
            f"MCP Wrapper: Preloaded {len(self._tool_definitions)} tool definitions."
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        这个包装器的退出逻辑是空的，因为底层会话的生命周期
        由创建它的工厂函数（baidu_map_factory）中的上下文管理器负责。
        """
        pass

    def to_api_tool(self, api_type: str) -> dict[str, Any]:
        """
        实现 MCPCompatible 协议。
        返回预加载的、符合API格式的工具定义。
        """
        if self._tool_definitions is None:
            raise RuntimeError(
                "Tool definitions were not loaded. Ensure you are using the wrapper in an 'async with' block."
            )

        if api_type == "gemini":
            return {"functionDeclarations": self._tool_definitions}
        else:
            return [
                {"type": "function", "function": tool_def}
                for tool_def in self._tool_definitions
            ]




_current_file_list: list[dict[str, Any]] | None = None


def set_current_file_list(file_list: list[dict[str, Any]] | None) -> None:
    """设置当前处理的文件列表"""
    global _current_file_list
    _current_file_list = file_list


def get_current_file_list() -> list[dict[str, Any]] | None:
    """获取当前处理的文件列表"""
    return _current_file_list


def _extract_image_base64_from_files() -> str | None:
    """从当前文件列表中提取第一张图片的base64数据"""
    if not _current_file_list:
        return None

    for file_info in _current_file_list:
        if isinstance(file_info.get("data"), bytes):
            file_type = file_info.get("type", "")
            if file_type.startswith("image/"):
                file_data = file_info["data"]
                return base64.b64encode(file_data).decode("utf-8")

    return None


def detect_intent_by_keywords(query: str) -> dict:
    """通过关键词匹配来检测用户意图。"""
    query_lower = query.lower()

    MAP_KEYWORDS = [
        "地图",
        "位置",
        "路线",
        "导航",
        "多远",
        "天气",
        "路况",
        "坐标",
        "地址",
        "怎么去",
        "到...要多久",
    ]
    SEARCH_KEYWORDS = ["搜索", "查找", "最新", "新闻", "实时", "今日", "搜一下", "新闻"]

    for keyword in MAP_KEYWORDS:
        if keyword in query_lower:
            return {"intent": "MAP"}

    for keyword in SEARCH_KEYWORDS:
        if keyword in query_lower:
            return {"intent": "SEARCH"}

    return {"intent": "CHAT"}


async def detect_function_calling_intent_with_ai(query: str) -> dict:
    """使用AI进行二次调用的精准意图检测 - 基于专家建议的混合架构

    Args:
        query: 用户查询文本

    Returns:
        dict: 包含意图分类结果和置信度的字典
    """
    from zhenxun.services.llm import chat

    intent_detection_prompt = f"""
你是一个专业的意图分类器。请分析用户查询并判断是否需要调用工具函数。

可用的工具类别：
1. MAP - 地图与地理位置相关查询，包括：
   • 地址坐标转换（地址转坐标、坐标转地址）
   • 地点查找（附近餐厅、某地在哪）
   • 路线导航（怎么去、多远、路线规划）
   • 实时信息（天气、路况、当前位置）

2. SEARCH - 网络信息搜索功能，仅用于以下情况：
   • 明确要求搜索网络信息（"搜索"、"查找"等明确指令）
   • 需要实时性、最新信息（"最新新闻"、"今日股价"、"实时数据"等）
   • 时效性强的信息查询（当前事件、最新动态等）

3. CHAT - 普通对话（例如：写作、编程、解释、分析、闲聊、计算等）

判断规则：
- 如果涉及地理位置、地点、路线、导航、距离、坐标、地址、天气等关键词，优先考虑MAP
- 如果明确要求搜索网络信息、查询资料、了解最新信息，选择SEARCH
- 其他情况选择CHAT

请严格按照以下JSON格式回复：
{{
    "intent": "MAP|SEARCH|CHAT",
    "confidence": 0.0-1.0,
    "reasoning": "判断理由"
}}

用户查询：{query}
"""

    try:
        logger.debug(
            f"意图检测LLM调用参数: model={base_config.get('auxiliary_llm_model')}"
        )
        response = await chat(
            intent_detection_prompt, model=base_config.get("auxiliary_llm_model")
        )

        import json
        import re

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())

            if all(key in result for key in ["intent", "confidence", "reasoning"]):
                needs_tools = result["intent"] in ["MAP", "SEARCH"]
                return {
                    "needs_tools": needs_tools,
                    "intent": result["intent"],
                    "confidence": result["confidence"],
                    "reasoning": result["reasoning"],
                }

        logger.warning("AI意图检测失败，默认使用标准聊天模式")
        return {
            "needs_tools": False,
            "intent": "UNKNOWN",
            "confidence": 0.5,
            "reasoning": "AI检测失败，默认使用标准聊天模式",
        }

    except Exception as e:
        logger.error(f"AI意图检测出错: {e}")
        return {
            "needs_tools": False,
            "intent": "UNKNOWN",
            "confidence": 0.5,
            "reasoning": f"检测出错: {e}，默认使用标准聊天模式",
        }


class BaiduMapConfig(BaseModel):
    command: str = Field(default="npx", description="执行命令")
    args: list[str] = Field(
        default_factory=lambda: ["-y", "@baidumap/mcp-server-baidu-map"],
        description="命令参数",
    )
    env: dict[str, str] | None = Field(None, description="环境变量")


@tool_registry.mcp_tool(name="baidu-map", config_model=BaiduMapConfig)
@asynccontextmanager
async def baidu_map_factory(config: BaiduMapConfig):
    """
    一个使用装饰器注册的 MCP 会话工厂。
    它使用 mcp.client.stdio.stdio_client 来启动子进程，
    并用我们的 MCPClientSessionWrapper 包装会话。
    """
    if not MCP_AVAILABLE:
        raise ImportError("无法创建 'baidu-map' 工具，因为 'mcp' 未安装。")

    server_params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            wrapper = MCPClientSessionWrapper(session)

            async with wrapper:
                yield wrapper
