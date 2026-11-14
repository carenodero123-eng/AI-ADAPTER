"""Stage D reliability: timeout, retry, circuit breaker, routing, and fallback."""

from __future__ import annotations

import asyncio
import logging

import pytest
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderCircuitOpenError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import ChatMessage
from app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from app.reliability.retry import RetryFailure, RetryManager, RetryPolicy
from app.reliability.router import ProviderRouter
from app.reliability.timeout import TimeoutManager
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


class ScriptedProvider(FakeProvider):
    """Fails a fixed number of times (or forever) before echoing locally."""

    def __init__(
        self,
        *,
        name: str = "primary",
        failures: int | None = None,
        error_type: type[Exception] = ProviderUnavailableError,
        message: str = "upstream unavailable",
        **kwargs,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self._remaining = failures
        self._error_type = error_type
        self._message = message
        self.calls = 0
        self.models_requested: list[str] = []

    async def generate(self, request):
        self.calls += 1
        self.models_requested.append(request.model)
        if self._remaining is None or self._remaining > 0:
            if self._remaining is not None:
                self._remaining -= 1
            raise self._error_type(self._message, provider=self.name)
        return await super().generate(request)


class SlowProvider(FakeProvider):
    def __init__(self, *, delay: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self._delay = delay

    async def generate(self, request):
        await asyncio.sleep(self._delay)
        return await super().generate(request)


class LiarProvider(FakeProvider):
    async def generate(self, request):
        result = await super().generate(request)
        return result.model_copy(update={"provider": "someone-else"})


async def _no_sleep(_: float) -> None:
    return None


def _retry_manager(max_attempts: int = 3) -> RetryManager:
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
        jitter_seconds=0.0,
    )
    return RetryManager(policy, sleep=_no_sleep, jitter_source=lambda: 0.0)


def _build_router(
    registry: ProviderRegistry,
    *,
    secondary: str | None = None,
    fallback: str | None = None,
    max_attempts: int = 3,
    threshold: int = 3,
    recovery: float = 30.0,
    timeout: float = 1.0,
) -> ProviderRouter:
    return ProviderRouter(
        registry,
        secondary_provider=secondary,
        fallback_provider=fallback,
        timeout_manager=TimeoutManager(timeout),
        retry_manager=_retry_manager(max_attempts),
        circuit_config=CircuitBreakerConfig(
            failure_threshold=threshold,
            recovery_timeout_seconds=recovery,
        ),
    )


async def _route(
    router: ProviderRouter,
    *,
    provider: str = "primary",
    model: str | None = None,
):
    return await router.generate(
        selected_provider=provider,
        model=model,
        messages=[ChatMessage(role="user", content="hello")],
        temperature=0.0,
        max_tokens=None,
        request_id="stage-d-request",
    )


def _make_app(registry: ProviderRegistry, **overrides) -> FastAPI:
    defaults = {
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
    }
    defaults.update(overrides)
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
        **defaults,
    )
    return create_app(settings, registry=registry)


def test_settings_validate_reliability_ranges() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reliability_max_attempts=0)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            reliability_backoff_base_seconds=5.0,
            reliability_backoff_max_seconds=1.0,
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reliability_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reliability_circuit_failure_threshold=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reliability_secondary_provider="Bad Name")


def test_reliability_provider_names_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        reliability_secondary_provider="  BACKUP ",
        reliability_fallback_provider="",
    )

    assert settings.reliability_secondary_provider == "backup"
    assert settings.reliability_fallback_provider == ""


def test_retry_policy_backoff_is_exponential_capped_and_jittered() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        base_delay_seconds=0.1,
        max_delay_seconds=0.5,
        jitter_seconds=0.05,
    )

    assert policy.delay_for(1, 0.0) == pytest.approx(0.1)
    assert policy.delay_for(2, 0.0) == pytest.approx(0.2)
    assert policy.delay_for(3, 0.0) == pytest.approx(0.4)
    assert policy.delay_for(4, 0.0) == pytest.approx(0.5)
    assert policy.delay_for(9, 0.0) == pytest.approx(0.5)
    assert policy.delay_for(1, 1.0) == pytest.approx(0.15)
    assert policy.delay_for(1, 5.0) == pytest.approx(0.15)
    assert policy.delay_for(4, 1.0) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="retry_number"):
        policy.delay_for(0, 0.0)


def test_retry_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=11)
    with pytest.raises(ValueError, match="must not exceed"):
        RetryPolicy(base_delay_seconds=2.0, max_delay_seconds=1.0)
    with pytest.raises(ValueError, match="jitter"):
        RetryPolicy(jitter_seconds=-1.0)


@pytest.mark.asyncio
async def test_retry_manager_backs_off_then_succeeds() -> None:
    sleeps: list[float] = []
    events: list[tuple[int, float, str]] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    manager = RetryManager(
        RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.1,
            max_delay_seconds=1.0,
            jitter_seconds=0.0,
        ),
        sleep=sleep,
        jitter_source=lambda: 0.0,
    )
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderUnavailableError("down", provider="primary")
        return "ok"

    outcome = await manager.run(
        operation,
        should_retry=lambda error: error.retryable,
        on_retry=lambda attempt, delay, error: events.append(
            (attempt, delay, error.code)
        ),
    )

    assert outcome.value == "ok"
    assert outcome.attempts == 3
    assert outcome.retry_count == 2
    assert sleeps == [pytest.approx(0.1), pytest.approx(0.2)]
    assert events == [
        (1, pytest.approx(0.1), "provider_unavailable"),
        (2, pytest.approx(0.2), "provider_unavailable"),
    ]


@pytest.mark.asyncio
async def test_retry_manager_bounds_attempts() -> None:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    manager = RetryManager(
        RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.0,
            max_delay_seconds=0.0,
            jitter_seconds=0.0,
        ),
        sleep=sleep,
    )
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise ProviderServerError("boom", provider="primary")

    with pytest.raises(RetryFailure) as info:
        await manager.run(operation, should_retry=lambda error: error.retryable)

    assert calls == 3
    assert info.value.attempts == 3
    assert info.value.retry_count == 2
    assert info.value.error.code == "provider_server_error"
    assert sleeps == [0.0, 0.0]


@pytest.mark.asyncio
async def test_retry_manager_stops_immediately_on_non_retryable_error() -> None:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    manager = RetryManager(RetryPolicy(max_attempts=5), sleep=sleep)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise ProviderAuthenticationError("bad key", provider="primary")

    with pytest.raises(RetryFailure) as info:
        await manager.run(operation, should_retry=lambda error: error.retryable)

    assert calls == 1
    assert info.value.attempts == 1
    assert info.value.retry_count == 0
    assert sleeps == []


@pytest.mark.asyncio
async def test_timeout_manager_converts_deadline_expiry() -> None:
    manager = TimeoutManager(0.01)

    async def slow() -> str:
        await asyncio.sleep(0.2)
        return "late"

    with pytest.raises(ProviderTimeoutError) as info:
        await manager.run(slow, provider="primary")

    assert info.value.provider == "primary"
    assert "deadline" in str(info.value)

    with pytest.raises(ValueError):
        TimeoutManager(0)


def test_circuit_opens_after_threshold_and_rejects_calls() -> None:
    clock = [100.0]
    breaker = CircuitBreaker(
        "primary",
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=10.0),
        clock=lambda: clock[0],
    )

    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == "closed"
    assert breaker.snapshot().failure_count == 1

    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == "open"

    breaker.record_failure()
    assert breaker.snapshot().failure_count == 2

    with pytest.raises(ProviderCircuitOpenError) as info:
        breaker.before_call()
    assert "retry after 10.0s" in str(info.value)
    assert info.value.provider == "primary"


def test_circuit_half_open_probe_and_recovery() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(
        "primary",
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=5.0),
        clock=lambda: clock[0],
    )

    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == "open"

    clock[0] = 5.0
    breaker.before_call()
    assert breaker.state == "half_open"

    with pytest.raises(ProviderCircuitOpenError, match="probe is already in flight"):
        breaker.before_call()

    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.snapshot().failure_count == 0


def test_circuit_reopens_when_half_open_probe_fails() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(
        "primary",
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=5.0),
        clock=lambda: clock[0],
    )
    breaker.before_call()
    breaker.record_failure()

    clock[0] = 6.0
    breaker.before_call()
    breaker.record_failure()

    assert breaker.state == "open"
    assert breaker.snapshot().failure_count == 2


def test_circuit_config_is_validated() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreakerConfig(failure_threshold=0)
    with pytest.raises(ValueError, match="recovery_timeout_seconds"):
        CircuitBreakerConfig(recovery_timeout_seconds=0)


@pytest.mark.asyncio
async def test_router_retries_primary_then_succeeds() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(
        failures=2,
        models=("primary-model",),
        default_model="primary-model",
    )
    registry.register(primary)
    router = _build_router(registry, max_attempts=3)

    route = await _route(router, model="primary-model")

    assert route.result.provider == "primary"
    assert route.requested_provider == "primary"
    assert route.providers_tried == ("primary",)
    assert route.retry_count == 2
    assert route.fallback_used is False
    assert route.fallback_reason is None
    assert primary.calls == 3
    assert primary.models_requested == ["primary-model"] * 3


@pytest.mark.asyncio
async def test_router_switches_to_secondary_with_model_remap() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(
        failures=None,
        models=("primary-model",),
        default_model="primary-model",
    )
    backup = ScriptedProvider(
        name="backup",
        failures=0,
        models=("backup-model",),
        default_model="backup-model",
    )
    registry.register(primary)
    registry.register(backup)
    registry.register(FakeProvider(name="fake"))
    router = _build_router(
        registry, secondary="backup", fallback="fake", max_attempts=2
    )

    route = await _route(router, model="primary-model")

    assert route.result.provider == "backup"
    assert route.result.model == "backup-model"
    assert route.providers_tried == ("primary", "backup")
    assert route.retry_count == 1
    assert route.fallback_used is True
    assert route.fallback_reason == "provider_unavailable"
    assert primary.calls == 2
    assert backup.models_requested == ["backup-model"]


@pytest.mark.asyncio
async def test_router_uses_deterministic_fallback_when_remote_providers_fail() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(failures=None)
    backup = ScriptedProvider(
        name="backup",
        failures=None,
        error_type=ProviderRateLimitError,
        message="slow down",
    )
    fallback = FakeProvider(name="fake")
    registry.register(primary)
    registry.register(backup)
    registry.register(fallback)
    router = _build_router(
        registry, secondary="backup", fallback="fake", max_attempts=2
    )

    route = await _route(router)

    assert route.result.provider == "fake"
    assert route.result.content == "[fake:fake-small] hello"
    assert route.providers_tried == ("primary", "backup", "fake")
    assert route.retry_count == 2
    assert route.fallback_used is True
    assert route.fallback_reason == "provider_rate_limit"
    assert (primary.calls, backup.calls) == (2, 2)


@pytest.mark.asyncio
async def test_router_raises_last_error_when_chain_is_exhausted() -> None:
    registry = ProviderRegistry()
    registry.register(ScriptedProvider(failures=None))
    registry.register(
        ScriptedProvider(
            name="backup",
            failures=None,
            error_type=ProviderRateLimitError,
            message="slow down",
        )
    )
    router = _build_router(
        registry, secondary="backup", fallback=None, max_attempts=1
    )

    with pytest.raises(ProviderRateLimitError) as info:
        await _route(router)

    assert info.value.code == "provider_rate_limit"
    assert info.value.provider == "backup"


@pytest.mark.asyncio
async def test_router_falls_back_immediately_on_authentication_failure() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(
        failures=None, error_type=ProviderAuthenticationError
    )
    fallback = FakeProvider(name="fake")
    registry.register(primary)
    registry.register(fallback)
    router = _build_router(registry, fallback="fake", max_attempts=3)

    route = await _route(router)

    assert route.result.provider == "fake"
    assert route.retry_count == 0
    assert route.fallback_reason == "provider_authentication_failed"
    assert primary.calls == 1
    assert router.circuit_snapshot("primary").failure_count == 1


@pytest.mark.asyncio
async def test_invalid_request_does_not_fall_back() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(
        failures=None, error_type=ProviderInvalidRequestError
    )
    fallback = ScriptedProvider(name="fallback", failures=0)
    registry.register(primary)
    registry.register(fallback)
    router = _build_router(registry, fallback="fallback", max_attempts=3)

    with pytest.raises(ProviderInvalidRequestError):
        await _route(router)

    assert primary.calls == 1
    assert fallback.calls == 0
    assert router.circuit_snapshot("primary").failure_count == 0


@pytest.mark.asyncio
async def test_open_circuit_skips_provider_without_calling_it() -> None:
    registry = ProviderRegistry()
    primary = ScriptedProvider(failures=None)
    fallback = FakeProvider(name="fake")
    registry.register(primary)
    registry.register(fallback)
    router = _build_router(
        registry, fallback="fake", max_attempts=3, threshold=1
    )

    first = await _route(router)
    second = await _route(router)

    assert first.result.provider == "fake"
    assert second.result.provider == "fake"
    assert primary.calls == 1
    snapshot = router.circuit_snapshot("primary")
    assert snapshot.state == "open"
    assert snapshot.failure_count == 1


@pytest.mark.asyncio
async def test_router_enforces_timeout_then_falls_back() -> None:
    registry = ProviderRegistry()
    registry.register(SlowProvider(name="primary", delay=0.2))
    registry.register(FakeProvider(name="fake"))
    router = _build_router(
        registry, fallback="fake", max_attempts=1, timeout=0.01
    )

    route = await _route(router)

    assert route.result.provider == "fake"
    assert route.fallback_reason == "provider_timeout"


@pytest.mark.asyncio
async def test_router_rejects_identity_mismatch_and_falls_back() -> None:
    registry = ProviderRegistry()
    registry.register(LiarProvider(name="primary"))
    registry.register(FakeProvider(name="fake"))
    router = _build_router(registry, fallback="fake", max_attempts=1)

    route = await _route(router)

    assert route.result.provider == "fake"
    assert route.fallback_reason == ProviderInvalidResponseError.code
    assert router.circuit_snapshot("primary").failure_count == 1


@pytest.mark.asyncio
async def test_router_rejects_unknown_selected_provider() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))
    router = _build_router(registry)

    with pytest.raises(ProviderNotFoundError):
        await _route(router, provider="ghost")


def test_router_rejects_unregistered_reliability_provider() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))

    with pytest.raises(ValueError, match="not registered"):
        _build_router(registry, secondary="ghost")


def test_circuit_snapshot_for_unknown_provider_raises_key_error() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))
    router = _build_router(registry)

    with pytest.raises(KeyError):
        router.circuit_snapshot("ghost")


@pytest.mark.asyncio
async def test_router_logs_codes_not_error_messages(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.reliability.router")
    registry = ProviderRegistry()
    registry.register(
        ScriptedProvider(
            failures=None,
            message="Bearer sk-secret-token was rejected",
        )
    )
    registry.register(FakeProvider(name="fake"))
    router = _build_router(registry, fallback="fake", max_attempts=2)

    await _route(router)

    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert "sk-secret-token" not in logged
    assert "provider_unavailable" in logged


def test_generation_api_reports_retry_metadata() -> None:
    registry = ProviderRegistry()
    registry.register(ScriptedProvider(name="flaky", failures=2))
    app = _make_app(
        registry,
        default_provider="flaky",
        reliability_max_attempts=3,
        reliability_fallback_provider="",
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "flaky"
    assert body["requested_provider"] == "flaky"
    assert body["retry_count"] == 2
    assert body["fallback_used"] is False
    assert body["fallback_reason"] is None
    assert body["providers_tried"] == ["flaky"]


def test_generation_api_reports_fallback_metadata() -> None:
    registry = ProviderRegistry()
    registry.register(ScriptedProvider(name="broken", failures=None))
    registry.register(FakeProvider(name="backup"))
    registry.register(FakeProvider(name="fake"))
    app = _make_app(
        registry,
        default_provider="broken",
        reliability_secondary_provider="backup",
        reliability_max_attempts=1,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "backup"
    assert body["requested_provider"] == "broken"
    assert body["fallback_used"] is True
    assert body["fallback_reason"] == "provider_unavailable"
    assert body["providers_tried"] == ["broken", "backup"]
    assert body["retry_count"] == 0


def test_generation_api_returns_normalized_error_when_chain_fails() -> None:
    registry = ProviderRegistry()
    registry.register(ScriptedProvider(name="broken", failures=None))
    registry.register(
        ScriptedProvider(name="backup", failures=None)
    )
    app = _make_app(
        registry,
        default_provider="broken",
        reliability_secondary_provider="backup",
        reliability_fallback_provider="",
        reliability_max_attempts=1,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"X-Request-ID": "exhausted-001"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "provider_unavailable"
    assert body["error"]["provider"] == "backup"
    assert body["error"]["retryable"] is True
    assert body["request_id"] == "exhausted-001"


def test_provider_health_reports_circuit_state() -> None:
    registry = ProviderRegistry()
    registry.register(ScriptedProvider(name="broken", failures=None))
    registry.register(FakeProvider(name="fake"))
    app = _make_app(
        registry,
        default_provider="broken",
        reliability_circuit_failure_threshold=1,
        reliability_max_attempts=1,
    )

    with TestClient(app) as client:
        generate = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        health = client.get("/api/v1/providers/broken/health")

    assert generate.status_code == 200
    assert health.status_code == 200
    circuit = health.json()["circuit"]
    assert circuit["state"] == "open"
    assert circuit["failure_count"] == 1
    assert 0.0 <= circuit["recovery_remaining_seconds"] <= 30.0


def test_app_state_exposes_provider_router(client) -> None:
    router = client.app.state.provider_router
    assert isinstance(router, ProviderRouter)
    assert router.fallback_provider == "fake"
    assert router.circuit_snapshot("fake").state == "closed"
