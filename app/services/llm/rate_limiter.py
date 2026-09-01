"""Async rate limiter for LLM API calls."""

import asyncio
import time
import random
from typing import Any, Callable, Coroutine
from loguru import logger


class LLMRateLimiter:
    """Controls concurrent LLM request volume with semaphore, cooldown, and exponential backoff.

    Args:
        max_concurrent: Maximum simultaneous LLM API calls.
        min_delay_seconds: Minimum gap between consecutive calls across all tasks.
        max_retries: Retry count on rate-limit (429) or transient network errors.
        base_backoff_seconds: Initial backoff wait in seconds (doubles each retry).
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        min_delay_seconds: float = 0.5,
        max_retries: int = 5,
        base_backoff_seconds: float = 2.0,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_delay = min_delay_seconds
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds
        self._last_call_time = 0.0
        self._lock = asyncio.Lock()

    async def execute(self, coro_factory: Callable[[], Coroutine[Any, Any, Any]], task_name: str = "") -> Any:
        """Execute a coroutine with concurrency throttling and retry logic.

        Args:
            coro_factory: Zero-argument callable that returns a fresh coroutine per attempt.
            task_name: Label for logging context.

        Returns:
            Result of the coroutine.
        """
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            async with self._semaphore:
                # Enforce minimum delay between calls globally
                async with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_call_time
                    if elapsed < self._min_delay:
                        await asyncio.sleep(self._min_delay - elapsed)
                    self._last_call_time = time.monotonic()

                try:
                    result = await coro_factory()
                    return result

                except Exception as exc:
                    last_error = exc
                    exc_str = str(exc).lower()
                    is_rate_limit = (
                        "429" in exc_str
                        or "rate" in exc_str
                        or "quota" in exc_str
                        or "resource_exhausted" in exc_str
                        or "too many requests" in exc_str
                    )

                    if is_rate_limit and attempt < self._max_retries:
                        backoff = self._base_backoff * (2 ** (attempt - 1))
                        jitter = random.uniform(0, backoff * 0.25)
                        wait = backoff + jitter
                        logger.warning(
                            f"[{task_name}] Rate limited (attempt {attempt}/{self._max_retries}), "
                            f"retrying in {wait:.1f}s: {exc}"
                        )
                        await asyncio.sleep(wait)
                    elif attempt < self._max_retries:
                        wait = self._base_backoff * attempt
                        logger.warning(
                            f"[{task_name}] Error (attempt {attempt}/{self._max_retries}), "
                            f"retrying in {wait:.1f}s: {exc}"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            f"[{task_name}] All {self._max_retries} attempts exhausted: {exc}"
                        )

        raise last_error  # type: ignore[misc]
