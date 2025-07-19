"""
通用 Agent 执行循环
"""

import json
from typing import Any

from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from zhenxun.services.llm import LLMMessage
from zhenxun.services.llm.tools import tool_registry
from zhenxun.services.log import logger

from ..config import base_config
from .session_manager import SessionState, SessionStatus, session_manager


async def _execute_mcp_tool(
    mcp_tool_name: str, sub_tool_name: str, arguments: dict[str, Any]
) -> Any:
    """
    一个独立的辅助函数，用于临时连接到MCP服务器并执行其提供的子工具。
    :param mcp_tool_name: 父MCP工具的名称 (如 'baidu-map')
    :param sub_tool_name: 要执行的子工具的名称 (如 'map_geocode')
    :param arguments: 子工具的参数
    """
    logger.info(
        f"⚡️ 执行 MCP 工具: {mcp_tool_name} -> {sub_tool_name}，参数: {arguments}"
    )
    try:
        from ..tools import MCP_AVAILABLE

        if not MCP_AVAILABLE:
            raise RuntimeError("尝试执行MCP工具，但'mcp'依赖未安装。")

        import mcp

        llm_tool = tool_registry.get_tool(mcp_tool_name)
        if not llm_tool.mcp_session or not callable(llm_tool.mcp_session):
            raise ValueError(
                f"工具 '{mcp_tool_name}' 不是一个有效的、可调用的MCP工具。"
            )

        session_factory = llm_tool.mcp_session

        async with session_factory() as mcp_session_wrapper:
            if not hasattr(mcp_session_wrapper, "session") or not isinstance(
                mcp_session_wrapper.session, mcp.ClientSession
            ):
                raise TypeError("无法从包装器中获取底层的 MCP ClientSession。")

            client_session: mcp.ClientSession = mcp_session_wrapper.session

            result = await client_session.call_tool(
                name=sub_tool_name, arguments=arguments
            )

            logger.info(f"✅ 工具 '{sub_tool_name}' 执行成功。")
            return result.model_dump()

    except Exception as e:
        logger.error(f"❌ 执行 MCP 工具 '{sub_tool_name}' 失败: {e}")
        return {"error": f"执行工具时发生错误: {e!s}"}


async def run_generic_agent_loop(
    session_state: SessionState,
    mcp_tool_name: str,
    system_prompt: str,
    bot: Bot,
    event: MessageEvent,
    model_name: str | None = None,
) -> str:
    """
    执行可暂停和恢复的通用Agent循环。
    """
    session_state.status = SessionStatus.PROCESSING_AGENT
    ai_instance = session_state.ai_instance
    conversation_history = ai_instance.history

    if not any(msg.role == "system" for msg in conversation_history):
        conversation_history.insert(0, LLMMessage.system(system_prompt))

    mcp_tools = tool_registry.get_tools([mcp_tool_name])

    for i in range(5):
        logger.info(
            f"🔄 Agent 循环 - 第 {i + 1}/5 轮，会话ID: {session_manager._get_session_id(event.get_user_id(), str(getattr(event, 'group_id', None)))}"
        )

        llm_response = await ai_instance.analyze(
            message=None,
            history=conversation_history,
            activated_tools=mcp_tools,
            model=model_name or base_config.get("AGENT_MODEL_NAME"),
        )

        if not llm_response.tool_calls:
            final_response_text = llm_response.text
            conversation_history.append(
                LLMMessage.assistant_text_response(final_response_text)
            )

            if final_response_text and final_response_text.strip().endswith(
                ("?", "？")
            ):
                logger.info("✅ Agent 正在等待用户输入以继续。")
                session_state.status = SessionStatus.AWAITING_USER_INPUT
            else:
                logger.info("✅ Agent 循环结束，模型已生成最终回复。")
                session_state.status = SessionStatus.IDLE
                session_state.intent = None
            return final_response_text

        conversation_history.append(
            LLMMessage.assistant_tool_calls(llm_response.tool_calls)
        )
        logger.info(f"⛏️ Agent 决定调用 {len(llm_response.tool_calls)} 个工具。")

        tool_results_messages = []
        for tool_call in llm_response.tool_calls:
            arguments = (
                json.loads(tool_call.function.arguments)
                if isinstance(tool_call.function.arguments, str)
                else tool_call.function.arguments
            )
            tool_result = await _execute_mcp_tool(
                mcp_tool_name=mcp_tool_name,
                sub_tool_name=tool_call.function.name,
                arguments=arguments,
            )
            tool_results_messages.append(
                LLMMessage.tool_response(
                    tool_call_id=tool_call.id,
                    function_name=tool_call.function.name,
                    result=tool_result,
                )
            )

        conversation_history.extend(tool_results_messages)

    logger.warning("Agent 循环达到最大次数，未能得出最终结论。")
    session_state.status = SessionStatus.IDLE
    session_state.intent = None
    return "抱歉，我多次尝试后仍然无法解决你的问题。请检查我的工具或稍后再试。"
