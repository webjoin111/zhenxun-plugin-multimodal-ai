"""
会话管理器 - 管理AI对话的上下文状态
"""

import asyncio
from dataclasses import dataclass
import time

from zhenxun.services.ai.context.memory.manager import memory_manager
from zhenxun.services.log import logger
from nonebot import get_driver

from .config import base_config


@dataclass
class SessionState:
    last_access_time: float = 0.0


class SessionManager:
    """AI会话管理器 - 管理用户的对话上下文"""

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval = 60

    def start_cleanup_task(self):
        """启动会话清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("会话清理任务已启动")

    def stop_cleanup_task(self):
        """停止会话清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("会话清理任务已停止")

    async def _cleanup_loop(self):
        """定期清理过期会话"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"会话清理任务出错: {e}")

    async def _cleanup_expired_sessions(self):
        """清理过期的会话"""
        if base_config.get("context_timeout_minutes") <= 0:
            return

        timeout_seconds = base_config.get("context_timeout_minutes") * 60
        current_time = time.time()

        expired_sessions = []
        for session_id, session_state in self._sessions.items():
            if current_time - session_state.last_access_time > timeout_seconds:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self._sessions[session_id]
            await memory_manager.cleaner().session(session_id).clear_short_term()
            logger.debug(f"清理过期会话: {session_id}")

        if expired_sessions:
            logger.info(f"清理了 {len(expired_sessions)} 个过期会话")

    def _get_session_id(self, user_id: str, group_id: str | None = None) -> str:
        """生成会话ID"""
        if group_id:
            return f"group_{group_id}_user_{user_id}"
        else:
            return f"user_{user_id}"

    async def touch_session(self, user_id: str, group_id: str | None = None) -> str:
        """更新会话最后访问时间并返回 session_id"""
        if base_config.get("context_timeout_minutes") <= 0:
            return self._get_session_id(user_id, group_id)

        session_id = self._get_session_id(user_id, group_id)
        current_time = time.time()

        if session_id in self._sessions:
            session_state = self._sessions[session_id]
            timeout_seconds = base_config.get("context_timeout_minutes") * 60

            if current_time - session_state.last_access_time <= timeout_seconds:
                session_state.last_access_time = current_time
                return session_id
            else:
                del self._sessions[session_id]
                await memory_manager.cleaner().session(session_id).clear_short_term()

        self._sessions[session_id] = SessionState(last_access_time=current_time)
        return session_id

    async def clear_session(self, user_id: str, group_id: str | None = None) -> bool:
        """清空指定用户的会话历史并重置状态"""
        session_id = self._get_session_id(user_id, group_id)

        if session_id in self._sessions:
            session_state = self._sessions[session_id]
            await memory_manager.cleaner().session(session_id).clear_short_term()
            session_state.last_access_time = time.time()
            logger.info(f"清空并重置会话状态: {session_id}")
            return True

        return False

    async def get_session_info(
        self, user_id: str, group_id: str | None = None
    ) -> dict | None:
        """获取会话信息"""
        session_id = self._get_session_id(user_id, group_id)

        if session_id in self._sessions:
            session_state = self._sessions[session_id]

            return {
                "session_id": session_id,
                "history_length": "未知(受新核心托管)",
                "last_access_time": session_state.last_access_time,
                "timeout_minutes": base_config.get("context_timeout_minutes"),
                "time_remaining": max(
                    0,
                    base_config.get("context_timeout_minutes") * 60
                    - (time.time() - session_state.last_access_time),
                ),
            }

        return None

    def get_all_sessions_count(self) -> int:
        """获取当前活跃会话数量"""
        return len(self._sessions)


session_manager = SessionManager()

driver = get_driver()


@driver.on_startup
async def _start_ai_session_cleanup():
    session_manager.start_cleanup_task()


@driver.on_shutdown
async def _stop_ai_session_cleanup():
    session_manager.stop_cleanup_task()
