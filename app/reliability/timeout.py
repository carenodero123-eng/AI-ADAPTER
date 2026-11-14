"""Bounded execution deadlines for provider calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.providers.errors import ProviderTimeoutError

T = TypeVar("T")


class TimeoutManager:
    """Cancel provider work that exceeds the configured deadline."""

    def __init__(self, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._timeout_seconds = timeout_seconds

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        provider: str,
    ) -> T:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await operation()
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Provider '{provider}' exceeded the "
                f"{self._timeout_seconds:g}s request deadline.",
                provider=provider,
            ) from exc
