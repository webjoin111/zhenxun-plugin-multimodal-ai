import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import time
from typing import Any

from zhenxun.services.log import logger


class RequestStatus(Enum):
    """请求状态枚举"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DrawRequest:
    """绘图请求数据类"""

    request_id: str
    user_id: str
    prompt: str
    status: RequestStatus = RequestStatus.PENDING
    created_at: datetime = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    estimated_wait_time: float = 0.0
    queue_position: int = 0
    image_path: str | None = None  # 添加图片路径字段

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    @property
    def wait_time(self) -> float:
        """实际等待时间（秒）"""
        if self.started_at:
            return (self.started_at - self.created_at).total_seconds()
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def processing_time(self) -> float:
        """处理时间（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0


class DrawQueueManager:
    """AI绘图队列管理器"""

    def __init__(self):
        self._queue: list[DrawRequest] = []
        self._processing_request: DrawRequest | None = None
        self._completed_requests: list[DrawRequest] = []
        self._lock = asyncio.Lock()
        self._processing_lock = asyncio.Lock()

        self._total_requests = 0
        self._average_processing_time = 60.0
        self._last_browser_close_time: datetime | None = None
        self._browser_cooldown_seconds = 180

        self._queue_processor_task: asyncio.Task | None = None
        self._shutdown = False

        logger.info("AI绘图队列管理器已初始化")

    def set_browser_cooldown(self, seconds: int):
        """设置浏览器冷却时间"""
        self._browser_cooldown_seconds = seconds
        logger.info(f"浏览器冷却时间已设置为 {seconds} 秒")

    def set_browser_close_time(self):
        """记录浏览器关闭时间"""
        self._last_browser_close_time = datetime.now()
        logger.info("浏览器关闭时间已记录，开始冷却期")

    def is_browser_in_cooldown(self) -> bool:
        """检查浏览器是否在冷却期"""
        if not self._last_browser_close_time:
            return False

        elapsed = (datetime.now() - self._last_browser_close_time).total_seconds()
        return elapsed < self._browser_cooldown_seconds

    def get_browser_cooldown_remaining(self) -> float:
        """获取浏览器冷却剩余时间（秒）"""
        if not self.is_browser_in_cooldown():
            return 0.0

        elapsed = (datetime.now() - self._last_browser_close_time).total_seconds()
        return max(0.0, self._browser_cooldown_seconds - elapsed)

    async def add_request(
        self, user_id: str, prompt: str, image_path: str | None = None
    ) -> DrawRequest:
        """添加绘图请求到队列"""
        async with self._lock:
            request_id = f"{user_id}_{int(time.time() * 1000)}"

            queue_position = len(self._queue)
            estimated_wait = queue_position * self._average_processing_time

            if self._processing_request:
                estimated_wait += max(
                    0,
                    self._average_processing_time
                    - self._processing_request.processing_time,
                )

            if self.is_browser_in_cooldown():
                estimated_wait += self.get_browser_cooldown_remaining()

            request = DrawRequest(
                request_id=request_id,
                user_id=user_id,
                prompt=prompt,
                estimated_wait_time=estimated_wait,
                image_path=image_path,
            )

            self._queue.append(request)
            self._total_requests += 1

            # 计算当前请求的实际队列位置
            actual_position = len(self._queue)

            logger.info(
                f"用户 {user_id} 的绘图请求已加入队列，位置: {actual_position}, 预估等待: {estimated_wait:.1f}秒"
            )

            # 将实际位置存储在请求对象中
            request.queue_position = actual_position
            return request

    async def get_next_request(self) -> DrawRequest | None:
        """获取下一个待处理的请求"""
        async with self._lock:
            if not self._queue:
                return None

            request = self._queue.pop(0)
            request.status = RequestStatus.PROCESSING
            request.started_at = datetime.now()
            self._processing_request = request

            logger.info(f"开始处理请求 {request.request_id}")
            return request

    async def complete_request(self, request: DrawRequest, result: dict[str, Any]):
        """完成请求处理"""
        async with self._lock:
            request.status = RequestStatus.COMPLETED
            request.completed_at = datetime.now()
            request.result = result

            processing_time = request.processing_time
            if processing_time > 0:
                self._average_processing_time = (
                    self._average_processing_time * 0.8 + processing_time * 0.2
                )

            self._completed_requests.append(request)
            self._processing_request = None

            logger.info(
                f"请求 {request.request_id} 处理完成，耗时: {processing_time:.1f}秒"
            )

    async def fail_request(self, request: DrawRequest, error: str):
        """标记请求失败"""
        async with self._lock:
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.now()
            request.error = error

            self._completed_requests.append(request)
            self._processing_request = None

            logger.error(f"请求 {request.request_id} 处理失败: {error}")

    async def cancel_request(self, request_id: str) -> bool:
        """取消请求"""
        async with self._lock:
            for i, request in enumerate(self._queue):
                if request.request_id == request_id:
                    request.status = RequestStatus.CANCELLED
                    self._queue.pop(i)
                    self._completed_requests.append(request)
                    logger.info(f"请求 {request_id} 已取消")
                    return True

            if (
                self._processing_request
                and self._processing_request.request_id == request_id
            ):
                logger.warning(f"请求 {request_id} 正在处理中，无法取消")
                return False

            return False

    def get_queue_status(self) -> dict[str, Any]:
        """获取队列状态"""
        return {
            "queue_length": len(self._queue),
            "processing_request": self._processing_request.request_id
            if self._processing_request
            else None,
            "total_requests": self._total_requests,
            "average_processing_time": self._average_processing_time,
            "browser_in_cooldown": self.is_browser_in_cooldown(),
            "browser_cooldown_remaining": self.get_browser_cooldown_remaining(),
        }

    def get_user_queue_position(self, user_id: str) -> int | None:
        """获取用户在队列中的位置（返回最新请求的位置）"""
        last_position = None
        for i, request in enumerate(self._queue):
            if request.user_id == user_id:
                last_position = i + 1
        return last_position

    def get_user_request_status(self, user_id: str) -> DrawRequest | None:
        """获取用户最新的请求状态"""
        if self._processing_request and self._processing_request.user_id == user_id:
            return self._processing_request

        for request in self._queue:
            if request.user_id == user_id:
                return request

        for request in reversed(self._completed_requests[-10:]):
            if request.user_id == user_id:
                return request

        return None

    async def wait_for_request_completion(
        self, request_id: str, timeout: float = 300.0
    ) -> DrawRequest | None:
        """等待特定请求完成"""
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # 检查是否在已完成的请求中
            for req in self._completed_requests:
                if req.request_id == request_id:
                    return req

            # 检查是否正在处理中
            if (
                self._processing_request
                and self._processing_request.request_id == request_id
            ):
                await asyncio.sleep(1)
                continue

            # 检查是否还在队列中
            for req in self._queue:
                if req.request_id == request_id:
                    await asyncio.sleep(1)
                    break
            else:
                # 请求不在队列中，可能已被取消或出错
                return None

        return None  # 超时

    async def process_queue_once(self):
        """处理队列中的一个请求（如果有的话）"""
        async with self._processing_lock:
            # 等待浏览器冷却结束
            while self.is_browser_in_cooldown():
                cooldown_remaining = self.get_browser_cooldown_remaining()
                logger.debug(
                    f"队列处理器等待浏览器冷却结束，剩余 {cooldown_remaining:.1f}秒"
                )
                await asyncio.sleep(min(5, cooldown_remaining))

            # 获取下一个请求
            current_request = await self.get_next_request()
            if not current_request:
                return None

            from ..draw import image_generator

            try:
                # 手动初始化浏览器
                await image_generator.initialize()

                # 执行生成和下载
                result = await image_generator.generate_image(
                    prompt=current_request.prompt,
                    count=1,
                    image_path=current_request.image_path,
                )
                await self.complete_request(current_request, result)

            except Exception as e:
                await self.fail_request(current_request, str(e))
                # 即使失败也要确保浏览器被清理
                raise
            finally:
                # 确保浏览器在任何情况下都被关闭
                await image_generator.cleanup()

            return current_request

    async def cleanup_old_requests(self, max_age_hours: int = 24):
        """清理旧的已完成请求"""
        async with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            original_count = len(self._completed_requests)

            self._completed_requests = [
                req
                for req in self._completed_requests
                if req.completed_at and req.completed_at > cutoff_time
            ]

            cleaned_count = original_count - len(self._completed_requests)
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个旧的请求记录")

    def start_queue_processor(self):
        """启动队列处理器"""
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._shutdown = False
            self._queue_processor_task = asyncio.create_task(
                self._queue_processor_loop()
            )
            logger.info("队列处理器已启动")

    async def stop_queue_processor(self):
        """停止队列处理器"""
        self._shutdown = True
        if self._queue_processor_task and not self._queue_processor_task.done():
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
            logger.info("队列处理器已停止")

    async def _queue_processor_loop(self):
        """队列处理器主循环"""
        logger.info("队列处理器主循环已启动")
        while not self._shutdown:
            try:
                if self._queue:  # 只有当队列不为空时才处理
                    await self.process_queue_once()
                else:
                    await asyncio.sleep(1)  # 队列为空时等待
            except Exception as e:
                logger.error(f"队列处理器发生错误: {e}")
                await asyncio.sleep(5)  # 出错时等待一段时间再继续


draw_queue_manager = DrawQueueManager()
