"""Per-provider circuit breaker with closed, open, and half-open states."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.providers.errors import ProviderCircuitOpenError

CircuitState = Literal["closed", "open", "half_open"]

logger = logging.getLogger("app.reliability.circuit")


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1 or self.failure_threshold > 20:
            raise ValueError("failure_threshold must be between 1 and 20")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be greater than zero")


@dataclass(frozen=True)
class CircuitSnapshot:
    provider: str
    state: CircuitState
    failure_count: int
    opened_at: float | None
    recovery_remaining_seconds: float | None


class CircuitBreaker:
    """Single-event-loop circuit breaker shared across requests.

    State transitions contain no awaits and are therefore atomic within the
    application event loop. A half-open circuit permits exactly one probe.
    """

    def __init__(
        self,
        provider: str,
        config: CircuitBreakerConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self._config = config
        self._clock = clock
        self._state: CircuitState = "closed"
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def state(self) -> CircuitState:
        return self._state

    def before_call(self) -> None:
        now = self._clock()
        if self._state == "open":
            remaining = self._recovery_remaining(now)
            if remaining > 0:
                raise ProviderCircuitOpenError(
                    f"Circuit breaker for provider '{self._provider}' is open; "
                    f"retry after {remaining:.1f}s.",
                    provider=self._provider,
                )
            self._state = "half_open"
            self._half_open_probe_in_flight = False
            logger.info(
                "circuit.half_open",
                extra={
                    "event": "circuit.half_open",
                    "provider": self._provider,
                },
            )

        if self._state == "half_open":
            if self._half_open_probe_in_flight:
                raise ProviderCircuitOpenError(
                    f"Circuit breaker for provider '{self._provider}' is "
                    "half-open and a probe is already in flight.",
                    provider=self._provider,
                )
            self._half_open_probe_in_flight = True

    def record_success(self) -> None:
        if self._state == "open":
            return
        was_half_open = self._state == "half_open"
        self._state = "closed"
        self._failure_count = 0
        self._opened_at = None
        self._half_open_probe_in_flight = False
        if was_half_open:
            logger.info(
                "circuit.closed",
                extra={
                    "event": "circuit.closed",
                    "provider": self._provider,
                },
            )

    def record_failure(self) -> None:
        if self._state == "open":
            return

        self._failure_count += 1
        if (
            self._state == "half_open"
            or self._failure_count >= self._config.failure_threshold
        ):
            self._open()

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = self._clock()
        self._half_open_probe_in_flight = False
        logger.warning(
            "circuit.opened",
            extra={
                "event": "circuit.opened",
                "provider": self._provider,
                "failure_count": self._failure_count,
                "recovery_timeout_seconds": (
                    self._config.recovery_timeout_seconds
                ),
            },
        )

    def _recovery_remaining(self, now: float) -> float:
        if self._opened_at is None:
            return 0.0
        return max(
            0.0,
            self._config.recovery_timeout_seconds
            - (now - self._opened_at),
        )

    def snapshot(self) -> CircuitSnapshot:
        now = self._clock()
        remaining = (
            self._recovery_remaining(now)
            if self._state == "open"
            else None
        )
        return CircuitSnapshot(
            provider=self._provider,
            state=self._state,
            failure_count=self._failure_count,
            opened_at=self._opened_at,
            recovery_remaining_seconds=remaining,
        )
