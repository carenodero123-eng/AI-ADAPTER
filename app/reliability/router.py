"""Provider routing with retries, circuit breaking, and deterministic fallback."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.providers.base import AIProvider
from app.providers.errors import (
    ProviderCircuitOpenError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
)
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    ChatMessage,
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitSnapshot,
)
from app.reliability.retry import RetryFailure, RetryManager
from app.reliability.timeout import TimeoutManager

logger = logging.getLogger("app.reliability.router")


class BudgetReservation(Protocol):
    """Opaque handle returned by an attempt budget."""


class AttemptBudget(Protocol):
    """Pre-call cost reservation contract used by the router."""

    async def reserve(
        self,
        provider: str,
        request: GenerationRequest,
        *,
        request_id: str,
    ) -> BudgetReservation: ...

    async def settle(
        self,
        reservation: BudgetReservation,
        usage: TokenUsage,
        *,
        request_id: str,
    ) -> None: ...

    async def release(
        self,
        reservation: BudgetReservation,
        *,
        request_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class RouteResult:
    result: GenerationResult
    requested_provider: str
    providers_tried: tuple[str, ...]
    retry_count: int
    fallback_used: bool
    fallback_reason: str | None


class ProviderRouter:
    """Execute one request through a bounded provider chain.

    The provider selected by the caller is tried first. A configured secondary
    provider is tried next, followed by a deterministic local fallback. Each
    provider gets at most the configured number of attempts, so the total work
    is strictly bounded.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        secondary_provider: str | None,
        fallback_provider: str | None,
        timeout_manager: TimeoutManager,
        retry_manager: RetryManager,
        circuit_config: CircuitBreakerConfig,
        breakers: Mapping[str, CircuitBreaker] | None = None,
        budget: AttemptBudget | None = None,
    ) -> None:
        for name in (secondary_provider, fallback_provider):
            if name is not None and name not in registry:
                raise ValueError(
                    f"Reliability provider '{name}' is not registered; "
                    f"available providers: {', '.join(registry.names)}"
                )

        self._registry = registry
        self._secondary_provider = secondary_provider or None
        self._fallback_provider = fallback_provider or None
        self._timeout = timeout_manager
        self._retry = retry_manager
        self._budget = budget
        self._breakers: dict[str, CircuitBreaker] = (
            dict(breakers) if breakers is not None else {}
        )
        for provider_name in registry.names:
            self._breakers.setdefault(
                provider_name,
                CircuitBreaker(provider_name, circuit_config),
            )

    @property
    def secondary_provider(self) -> str | None:
        return self._secondary_provider

    @property
    def fallback_provider(self) -> str | None:
        return self._fallback_provider

    def _chain(self, primary: str) -> tuple[str, ...]:
        names = [primary]
        for name in (self._secondary_provider, self._fallback_provider):
            if name is not None and name not in names:
                names.append(name)
        return tuple(names)

    @staticmethod
    def _model_for(
        provider: AIProvider,
        requested_model: str | None,
        *,
        primary: bool,
    ) -> str:
        if requested_model is None:
            return provider.default_model
        if primary or requested_model in provider.models:
            return requested_model
        return provider.default_model

    @staticmethod
    def _should_retry(error: ProviderError) -> bool:
        return error.retryable and not isinstance(
            error, ProviderCircuitOpenError
        )

    @staticmethod
    def _counts_as_failure(error: ProviderError) -> bool:
        return not isinstance(
            error, (ProviderInvalidRequestError, ProviderCircuitOpenError)
        )

    async def _attempt(
        self,
        provider: AIProvider,
        request: GenerationRequest,
        *,
        request_id: str,
    ) -> GenerationResult:
        breaker = self._breakers[provider.name]
        reservation: BudgetReservation | None = None
        if self._budget is not None:
            reservation = await self._budget.reserve(
                provider.name, request, request_id=request_id
            )

        settled = False
        try:
            breaker.before_call()
            try:
                result = await self._timeout.run(
                    lambda: provider.generate(request),
                    provider=provider.name,
                )
            except ProviderError as error:
                if self._counts_as_failure(error):
                    breaker.record_failure()
                raise
            except Exception:
                breaker.record_failure()
                raise

            if result.provider != provider.name:
                breaker.record_failure()
                if reservation is not None:
                    await self._budget.settle(
                        reservation, result.usage, request_id=request_id
                    )
                    settled = True
                raise ProviderInvalidResponseError(
                    "Provider result did not match the provider identity.",
                    provider=provider.name,
                )

            if reservation is not None:
                await self._budget.settle(
                    reservation, result.usage, request_id=request_id
                )
                settled = True
            breaker.record_success()
            return result
        finally:
            if reservation is not None and not settled:
                await self._budget.release(reservation, request_id=request_id)

    async def generate(
        self,
        *,
        selected_provider: str,
        model: str | None,
        messages: Sequence[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        request_id: str,
    ) -> RouteResult:
        primary = self._registry.get(selected_provider)
        primary_name = primary.name
        chain = self._chain(primary_name)
        providers_tried: list[str] = []
        retry_count = 0
        last_error: ProviderError | None = None

        for index, provider_name in enumerate(chain):
            provider = self._registry.get(provider_name)
            providers_tried.append(provider.name)
            selected_model = self._model_for(
                provider,
                model,
                primary=provider.name == primary_name,
            )
            provider_request = GenerationRequest(
                model=selected_model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )

            def on_retry(
                failed_attempt: int,
                delay_seconds: float,
                error: ProviderError,
                *,
                _provider_name: str = provider.name,
            ) -> None:
                logger.warning(
                    "provider.retry",
                    extra={
                        "event": "provider.retry",
                        "request_id": request_id,
                        "provider": _provider_name,
                        "failed_attempt": failed_attempt,
                        "next_attempt": failed_attempt + 1,
                        "delay_ms": round(delay_seconds * 1000, 3),
                        "error_code": error.code,
                    },
                )

            try:
                outcome = await self._retry.run(
                    lambda provider=provider, provider_request=provider_request: (
                        self._attempt(
                            provider, provider_request, request_id=request_id
                        )
                    ),
                    should_retry=self._should_retry,
                    on_retry=on_retry,
                )
            except RetryFailure as failure:
                retry_count += failure.retry_count
                last_error = failure.error
                logger.warning(
                    "provider.route.provider_failed",
                    extra={
                        "event": "provider.route.provider_failed",
                        "request_id": request_id,
                        "requested_provider": primary_name,
                        "provider": provider.name,
                        "attempts": failure.attempts,
                        "retry_count": failure.retry_count,
                        "error_code": failure.error.code,
                        "remaining_providers": len(chain) - index - 1,
                    },
                )
                if isinstance(failure.error, ProviderInvalidRequestError):
                    # A rejected request would be rejected by every provider;
                    # falling back would mask a client error as a success.
                    raise failure.error from failure
                continue

            retry_count += outcome.retry_count
            fallback_used = provider.name != primary_name
            fallback_reason = (
                last_error.code
                if fallback_used and last_error is not None
                else None
            )
            result = RouteResult(
                result=outcome.value,
                requested_provider=primary_name,
                providers_tried=tuple(providers_tried),
                retry_count=retry_count,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )
            logger.info(
                "provider.route.completed",
                extra={
                    "event": "provider.route.completed",
                    "request_id": request_id,
                    "requested_provider": primary_name,
                    "provider": provider.name,
                    "model": selected_model,
                    "providers_tried": list(providers_tried),
                    "retry_count": retry_count,
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                },
            )
            return result

        if last_error is None:
            raise ProviderInvalidResponseError(
                "Provider routing produced no result.",
                provider=primary_name,
            )

        logger.warning(
            "provider.route.exhausted",
            extra={
                "event": "provider.route.exhausted",
                "request_id": request_id,
                "requested_provider": primary_name,
                "providers_tried": list(providers_tried),
                "retry_count": retry_count,
                "fallback_attempted": len(chain) > 1,
                "error_code": last_error.code,
            },
        )
        # Callers that recover from exhaustion need to report which providers
        # were tried; the normalized error types keep their original shape.
        last_error.route_requested_provider = primary_name
        last_error.route_providers_tried = tuple(providers_tried)
        last_error.route_retry_count = retry_count
        raise last_error

    def circuit_snapshot(self, provider_name: str) -> CircuitSnapshot:
        breaker = self._breakers.get(provider_name)
        if breaker is None:
            raise KeyError(provider_name)
        return breaker.snapshot()
