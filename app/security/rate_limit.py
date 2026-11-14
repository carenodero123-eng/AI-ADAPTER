"""In-process fixed-window rate limiting."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.security.errors import RateLimitExceededError


@dataclass(frozen=True)
class RateLimitDecision:
    limit: int
    remaining: int
    reset_after_seconds: float


class RateLimiter:
    """Fixed-window limiter keyed by identity or client address.

    State is process local. Multi-process deployments need a shared limiter at
    the gateway or a shared store; this component guarantees atomic decisions
    within one application event loop.
    """

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 0:
            raise ValueError("max_requests must not be negative")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    @property
    def enabled(self) -> bool:
        return self._max_requests > 0

    async def check(self, key: str) -> RateLimitDecision | None:
        if not self.enabled:
            return None

        async with self._lock:
            now = self._clock()
            window_start, count = self._windows.get(key, (now, 0))
            if now - window_start >= self._window_seconds:
                window_start, count = now, 0

            if count >= self._max_requests:
                raise RateLimitExceededError(
                    retry_after_seconds=self._window_seconds - (now - window_start),
                    limit=self._max_requests,
                )

            count += 1
            self._windows[key] = (window_start, count)
            if len(self._windows) > 4096:
                self._prune(now)

            return RateLimitDecision(
                limit=self._max_requests,
                remaining=self._max_requests - count,
                reset_after_seconds=self._window_seconds - (now - window_start),
            )

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, (started, _) in self._windows.items()
            if now - started >= self._window_seconds
        ]
        for key in expired:
            del self._windows[key]
