"""Build reliability components from application settings."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.registry import ProviderRegistry
from app.reliability.circuit_breaker import CircuitBreakerConfig
from app.reliability.retry import RetryManager, RetryPolicy
from app.reliability.router import AttemptBudget, ProviderRouter
from app.reliability.timeout import TimeoutManager


def build_provider_router(
    settings: Settings,
    registry: ProviderRegistry,
    *,
    budget: AttemptBudget | None = None,
) -> ProviderRouter:
    return ProviderRouter(
        registry,
        secondary_provider=settings.reliability_secondary_provider or None,
        fallback_provider=settings.reliability_fallback_provider or None,
        timeout_manager=TimeoutManager(settings.reliability_timeout_seconds),
        retry_manager=RetryManager(
            RetryPolicy(
                max_attempts=settings.reliability_max_attempts,
                base_delay_seconds=settings.reliability_backoff_base_seconds,
                max_delay_seconds=settings.reliability_backoff_max_seconds,
                jitter_seconds=settings.reliability_jitter_seconds,
            )
        ),
        circuit_config=CircuitBreakerConfig(
            failure_threshold=settings.reliability_circuit_failure_threshold,
            recovery_timeout_seconds=settings.reliability_circuit_recovery_seconds,
        ),
        budget=budget,
    )
