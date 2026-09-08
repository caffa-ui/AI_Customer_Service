import asyncio
from collections import deque
import time


class LoginRateLimiter:
    """单进程登录失败限流；与当前固定单worker部署边界一致"""

    def __init__(self, *, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    def _prune(self, attempts: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while attempts and attempts[0] <= threshold:
            attempts.popleft()

    async def retry_after(self, key: str) -> int | None:
        now = time.monotonic()
        async with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None:
                return None
            self._prune(attempts, now)
            if not attempts:
                del self._attempts[key]
                return None
            if len(attempts) < self.max_attempts:
                return None
            return max(1, int(attempts[0] + self.window_seconds - now) + 1)

    async def record_failure(self, key: str) -> None:
        now = time.monotonic()
        async with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            self._prune(attempts, now)
            attempts.append(now)

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._attempts.pop(key, None)
