"""Stage E cost estimation, budget enforcement, and router integration."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.budget.errors import BudgetExceededError
from app.budget.estimation import estimate_prompt_tokens
from app.budget.factory import build_budget_manager
from app.budget.manager import BudgetManager
from app.budget.pricing import PricingRates
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import ProviderUnavailableError
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import ChatMessage, GenerationRequest, TokenUsage
from app.reliability.circuit_breaker import CircuitBreakerConfig
from app.reliability.retry import RetryManager, RetryPolicy
from app.reliability.router import ProviderRouter
from app.reliability.timeout import TimeoutManager
from fastapi.testclient import TestClient
from pydantic import ValidationError

MILLION = Decimal("1000000")


def _rates(per_million: str = "1000000") -> PricingRates:
    value = Decimal(per_million)
    return PricingRates(input_per_million_usd=value, output_per_million_usd=value)


def _request(max_tokens: int = 10) -> GenerationRequest:
    return GenerationRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hello")],
        max_tokens=max_tokens,
    )


def _manager(
    *,
    per_request: str = "100",
    daily: str = "100",
    monthly: str = "100",
    enforce: bool = True,
    clock=None,
    pricing: dict[str, PricingRates] | None = None,
) -> BudgetManager:
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    return BudgetManager(
        pricing=pricing or {"p": _rates()},
        per_request_limit_usd=Decimal(per_request),
        daily_limit_usd=Decimal(daily),
        monthly_limit_usd=Decimal(monthly),
        assumed_completion_tokens=10,
        enforce=enforce,
        **kwargs,
    )


def _usage(prompt: int = 6, completion: int = 5) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
    )


class _RecordingBudget:
    def __init__(self, reject_provider: str | None = None) -> None:
        self.reserved: list[str] = []
        self.settled: list[tuple[str, int]] = []
        self.released: list[str] = []
        self._reject_provider = reject_provider

    async def reserve(self, provider, request, *, request_id):
        self.reserved.append(provider)
        if provider == self._reject_provider:
            raise BudgetExceededError("per_request")
        return provider

    async def settle(self, reservation, usage, *, request_id):
        self.settled.append((reservation, usage.total_tokens))

    async def release(self, reservation, *, request_id):
        self.released.append(reservation)


class _FlakyFake(FakeProvider):
    def __init__(self, failures: int, *, name: str = "primary") -> None:
        super().__init__(name=name)
        self.remaining = failures
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if self.remaining:
            self.remaining -= 1
            raise ProviderUnavailableError("scripted failure")
        return await super().generate(request)


async def _generate(router: ProviderRouter, *, provider: str = "primary"):
    return await router.generate(
        selected_provider=provider,
        model=None,
        messages=[ChatMessage(role="user", content="hello")],
        temperature=0.0,
        max_tokens=10,
        request_id="r1",
    )


def _router(
    registry: ProviderRegistry,
    *,
    budget,
    attempts: int = 2,
    secondary: str = "",
    fallback: str = "",
) -> ProviderRouter:
    return ProviderRouter(
        registry,
        secondary_provider=secondary or None,
        fallback_provider=fallback or None,
        timeout_manager=TimeoutManager(5.0),
        retry_manager=RetryManager(
            RetryPolicy(max_attempts=attempts, base_delay_seconds=0)
        ),
        circuit_config=CircuitBreakerConfig(
            failure_threshold=10, recovery_timeout_seconds=30
        ),
        budget=budget,
    )


def test_pricing_cost_is_quantized_to_microdollars() -> None:
    rates = PricingRates(
        input_per_million_usd=Decimal("0.15"),
        output_per_million_usd=Decimal("0.60"),
    )
    assert rates.cost(0, 0) == Decimal("0.000000")
    assert rates.cost(1_000_000, 0) == Decimal("0.150000")
    assert rates.cost(1, 2) == Decimal("0.000001")
    assert PricingRates.free().cost(10_000, 10_000) == Decimal("0.000000")
    with pytest.raises(ValidationError):
        PricingRates(
            input_per_million_usd=Decimal("-1"),
            output_per_million_usd=Decimal("0"),
        )


def test_prompt_token_estimation_is_deterministic() -> None:
    messages = [
        ChatMessage(role="system", content="a"),
        ChatMessage(role="user", content="four"),
    ]
    assert estimate_prompt_tokens(messages) == 5 + 5
    assert estimate_prompt_tokens([]) == 0


def test_reserve_settle_and_release_track_spend() -> None:
    async def scenario() -> None:
        manager = _manager()
        reservation = await manager.reserve("p", _request(), request_id="r1")
        assert reservation.estimated_cost_usd == Decimal("16.000000")
        assert manager.snapshot().reserved_today_usd == Decimal("16.000000")

        await manager.settle(reservation, _usage(), request_id="r1")
        snapshot = manager.snapshot()
        assert snapshot.reserved_today_usd == Decimal("0.000000")
        assert snapshot.spent_today_usd == Decimal("11.000000")
        assert snapshot.spent_month_usd == Decimal("11.000000")

        released = await manager.reserve("p", _request(), request_id="r2")
        await manager.release(released, request_id="r2")
        assert manager.snapshot().reserved_today_usd == Decimal("0.000000")

    asyncio.run(scenario())


def test_per_request_limit_rejects_before_reserving() -> None:
    async def scenario() -> None:
        manager = _manager(per_request="10")
        with pytest.raises(BudgetExceededError) as info:
            await manager.reserve("p", _request(), request_id="r1")
        assert info.value.code == "budget_exceeded"
        assert info.value.status_code == 402
        assert "per-request" in info.value.message
        assert manager.snapshot().reserved_today_usd == Decimal("0.000000")

    asyncio.run(scenario())


def test_daily_limit_accounts_for_in_flight_reservations() -> None:
    async def scenario() -> None:
        manager = _manager(daily="20")
        await manager.reserve("p", _request(), request_id="r1")
        with pytest.raises(BudgetExceededError) as info:
            await manager.reserve("p", _request(), request_id="r2")
        assert "daily" in info.value.message.lower()
        assert manager.snapshot().reserved_today_usd == Decimal("16.000000")

    asyncio.run(scenario())


def test_monthly_limit_is_enforced() -> None:
    async def scenario() -> None:
        manager = _manager(daily="100", monthly="20")
        await manager.reserve("p", _request(), request_id="r1")
        with pytest.raises(BudgetExceededError) as info:
            await manager.reserve("p", _request(), request_id="r2")
        assert "monthly" in info.value.message.lower()

    asyncio.run(scenario())


def test_concurrent_reservations_cannot_overspend() -> None:
    async def scenario() -> None:
        manager = _manager(daily="20")
        outcomes = await asyncio.gather(
            manager.reserve("p", _request(), request_id="a"),
            manager.reserve("p", _request(), request_id="b"),
            return_exceptions=True,
        )
        assert sum(isinstance(item, BudgetExceededError) for item in outcomes) == 1
        assert manager.snapshot().reserved_today_usd == Decimal("16.000000")

    asyncio.run(scenario())


def test_daily_and_monthly_counters_roll_over() -> None:
    async def scenario() -> None:
        now = [datetime(2026, 1, 31, 23, 0, tzinfo=UTC)]
        manager = _manager(
            daily="100", monthly="1000", clock=lambda: now[0]
        )
        reservation = await manager.reserve("p", _request(), request_id="r1")
        now[0] = datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
        await manager.release(reservation, request_id="r1")

        snapshot = manager.snapshot()
        assert snapshot.day.isoformat() == "2026-02-01"
        assert snapshot.month == (2026, 2)
        assert snapshot.spent_today_usd == Decimal("0.000000")
        assert snapshot.reserved_today_usd == Decimal("0.000000")
        assert snapshot.spent_month_usd == Decimal("0.000000")
        assert snapshot.reserved_month_usd == Decimal("0.000000")

    asyncio.run(scenario())


def test_enforcement_can_be_disabled() -> None:
    async def scenario() -> None:
        manager = _manager(per_request="1", daily="1", monthly="1", enforce=False)
        assert manager.enforcement_enabled is False
        reservation = await manager.reserve("p", _request(), request_id="r1")
        assert manager.snapshot().reserved_today_usd == Decimal("0.000000")
        await manager.settle(reservation, _usage(), request_id="r1")
        assert manager.snapshot().spent_today_usd == Decimal("11.000000")

    asyncio.run(scenario())


def test_unknown_provider_is_priced_as_free() -> None:
    manager = _manager()
    assert manager.rates_for("unknown") == PricingRates.free()
    assert manager.actual_cost("unknown", _usage()) == Decimal("0.000000")


def test_budget_factory_maps_registered_pricing() -> None:
    pricing = {
        "fake": PricingRates(
            input_per_million_usd=Decimal("0.15"),
            output_per_million_usd=Decimal("0.60"),
        )
    }
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        budget_provider_pricing=pricing,
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    manager = build_budget_manager(settings, registry)
    assert manager.rates_for("fake") == pricing["fake"]
    assert manager.rates_for("unregistered") == PricingRates.free()


def test_budget_settings_are_validated() -> None:
    with pytest.raises(ValidationError, match="budget_per_request_usd"):
        Settings(
            _env_file=None,
            budget_per_request_usd=Decimal("60"),
            budget_daily_usd=Decimal("50"),
        )
    with pytest.raises(ValidationError, match="budget_daily_usd"):
        Settings(
            _env_file=None,
            budget_daily_usd=Decimal("600"),
            budget_monthly_usd=Decimal("500"),
        )


def test_budget_pricing_accepts_json_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "BUDGET_PROVIDER_PRICING",
        json.dumps({"custom": {"input_per_million_usd": 1.5, "output_per_million_usd": 2}}),
    )
    settings = Settings(_env_file=None, environment="test", log_level="WARNING")
    rates = settings.budget_provider_pricing["custom"]
    assert rates.input_per_million_usd == Decimal("1.5")
    assert rates.output_per_million_usd == Decimal("2")


def _api_settings(**overrides) -> Settings:
    values = {
        "security_require_auth": False,
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
        "log_level": "INFO",
        "log_format": "console",
    }
    values.update(overrides)
    return Settings(
        _env_file=None,
        environment="test",
        **values,
    )


def test_api_returns_402_when_budget_is_exceeded() -> None:
    settings = _api_settings(
        budget_per_request_usd=Decimal("0.000001"),
        budget_daily_usd=Decimal("1"),
        budget_monthly_usd=Decimal("10"),
        budget_provider_pricing={"fake": _rates()},
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert response.json()["error"]["retryable"] is False
    assert response.json()["request_id"]


def test_api_reports_cost_and_logs_request_summary(caplog) -> None:
    caplog.set_level(logging.INFO)
    settings = _api_settings(
        budget_provider_pricing={
            "fake": PricingRates(
                input_per_million_usd=Decimal("0.15"),
                output_per_million_usd=Decimal("0.60"),
            )
        }
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/generate",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 16,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_usd"] >= 0.0
    assert payload["cost_usd"] < 0.01

    summaries = [
        record for record in caplog.records if record.name == "app.api.generation"
    ]
    assert summaries
    summary = summaries[-1]
    assert summary.request_id == payload["request_id"]
    assert summary.provider == payload["provider"]
    assert summary.model == payload["model"]
    assert summary.cost_usd == payload["cost_usd"]
    assert summary.retry_count == payload["retry_count"]
    assert summary.fallback_used == payload["fallback_used"]
    assert summary.duration_ms >= 0.0
    assert "prompt" not in summary.__dict__
    assert "hello" not in " ".join(str(record.__dict__) for record in caplog.records)


def test_router_reserves_every_attempt_and_settles_success() -> None:
    async def scenario() -> None:
        provider = _FlakyFake(failures=1)
        registry = ProviderRegistry()
        registry.register(provider)
        budget = _RecordingBudget()
        router = _router(registry, budget=budget)

        route = await _generate(router)

        assert route.result.provider == "primary"
        assert budget.reserved == ["primary", "primary"]
        assert budget.released == ["primary"]
        assert budget.settled == [("primary", route.result.usage.total_tokens)]

    asyncio.run(scenario())


def test_router_releases_all_attempts_when_chain_fails() -> None:
    async def scenario() -> None:
        provider = _FlakyFake(failures=10)
        registry = ProviderRegistry()
        registry.register(provider)
        budget = _RecordingBudget()
        router = _router(registry, budget=budget, attempts=2)

        with pytest.raises(ProviderUnavailableError):
            await _generate(router)

        assert budget.reserved == ["primary", "primary"]
        assert budget.released == ["primary", "primary"]
        assert budget.settled == []

    asyncio.run(scenario())


def test_budget_error_aborts_chain_without_calling_fallback() -> None:
    async def scenario() -> None:
        fallback = _FlakyFake(failures=0, name="fake")
        primary = _FlakyFake(failures=0)
        registry = ProviderRegistry()
        registry.register(fallback)
        registry.register(primary)
        budget = _RecordingBudget(reject_provider="primary")
        router = _router(registry, budget=budget, fallback="fake")

        with pytest.raises(BudgetExceededError):
            await _generate(router)

        assert fallback.calls == 0
        assert budget.reserved == ["primary"]
        assert budget.settled == []
        assert budget.released == []

    asyncio.run(scenario())


def test_router_settles_with_fallback_identity() -> None:
    async def scenario() -> None:
        registry = ProviderRegistry()
        registry.register(_FlakyFake(failures=10))
        registry.register(FakeProvider())
        budget = _RecordingBudget()
        router = _router(registry, budget=budget, attempts=2, fallback="fake")

        route = await _generate(router)

        assert route.result.provider == "fake"
        assert budget.reserved == ["primary", "primary", "fake"]
        assert budget.released == ["primary", "primary"]
        assert budget.settled == [("fake", route.result.usage.total_tokens)]

    asyncio.run(scenario())
