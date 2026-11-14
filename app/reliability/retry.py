"""Bounded retries with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.providers.errors import ProviderError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    jitter_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must not be negative")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError(
                "base_delay_seconds must not exceed max_delay_seconds"
            )
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds must not be negative")

    def delay_for(self, retry_number: int, jitter_fraction: float) -> float:
        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        exponential = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (retry_number - 1)),
        )
        bounded_fraction = min(1.0, max(0.0, jitter_fraction))
        return min(
            self.max_delay_seconds,
            exponential + self.jitter_seconds * bounded_fraction,
        )


@dataclass(frozen=True)
class RetryOutcome[T]:
    value: T
    attempts: int
    retry_count: int


class RetryFailure(Exception):
    """The final provider error plus bounded-attempt metadata."""

    def __init__(
        self,
        error: ProviderError,
        *,
        attempts: int,
        retry_count: int,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.attempts = attempts
        self.retry_count = retry_count


class RetryManager:
    """Execute one provider attempt loop with a hard attempt ceiling."""

    def __init__(
        self,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_source: Callable[[], float] = random.random,
    ) -> None:
        self._policy = policy
        self._sleep = sleep
        self._jitter_source = jitter_source

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        should_retry: Callable[[ProviderError], bool],
        on_retry: Callable[[int, float, ProviderError], None] | None = None,
    ) -> RetryOutcome[T]:
        attempts = 0
        while True:
            attempts += 1
            try:
                value = await operation()
                return RetryOutcome(
                    value=value,
                    attempts=attempts,
                    retry_count=attempts - 1,
                )
            except ProviderError as error:
                if attempts >= self._policy.max_attempts or not should_retry(error):
                    raise RetryFailure(
                        error,
                        attempts=attempts,
                        retry_count=attempts - 1,
                    ) from error

                delay = self._policy.delay_for(
                    attempts, self._jitter_source()
                )
                if on_retry is not None:
                    on_retry(attempts, delay, error)
                await self._sleep(delay)
