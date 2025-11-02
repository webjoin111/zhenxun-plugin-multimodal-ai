"""
意图检测模块

提供基于关键词和AI的用户意图检测功能。
"""

from zhenxun.services.log import logger
from ..config import base_config


def detect_intent_by_keywords(query: str) -> dict:
    """通过关键词匹配来检测用户意图。"""
    query_lower = query.lower()


    SEARCH_KEYWORDS = ["搜索", "查找", "最新", "新闻", "实时", "今日", "搜一下", "新闻"]

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
1. SEARCH - 网络信息搜索功能，仅用于以下情况：
   • 明确要求搜索网络信息（"搜索"、"查找"等明确指令）
   • 需要实时性、最新信息（"最新新闻"、"今日股价"、"实时数据"等）
   • 时效性强的信息查询（当前事件、最新动态等）

2. CHAT - 普通对话（例如：写作、编程、解释、分析、闲聊、计算等）

判断规则：
- 如果明确要求搜索网络信息、查询资料、了解最新信息，选择SEARCH
- 其他情况选择CHAT

请严格按照以下JSON格式回复：
{{
    "intent": "SEARCH|CHAT",
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
            intent_detection_prompt, model=base_config.get("auxiliary_llm_model"),
        )

        import json
        import re

        json_match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())

            if all(key in result for key in ["intent", "confidence", "reasoning"]):
                needs_tools = result["intent"] == "SEARCH"
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