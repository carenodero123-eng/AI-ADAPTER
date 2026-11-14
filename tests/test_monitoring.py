"""Stage K cost, latency, report, and Prometheus metric tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.api.schemas.monitoring import performance_summary
from app.core.config import Settings
from app.database.engine import DatabaseManager
from app.database.records import RequestLogEntry
from app.database.repository import RequestLogRepository
from app.database.service import RequestLogService
from app.main import create_app
from app.monitoring.errors import MonitoringUnavailableError
from app.monitoring.metrics import MetricsCollector
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import MonitoringService
from fastapi.testclient import TestClient
from pydantic import ValidationError

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
USER_KEY = "user-key-0123456789abcdef"
ADMIN_KEY = "admin-key-0123456789abcdef"


def _settings(**overrides) -> Settings:
    values = {
        "database_enabled": True,
        "database_url": "sqlite+aiosqlite:///:memory:",
        "database_auto_create": True,
        "security_require_auth": False,
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
        "log_level": "ERROR",
        "log_format": "console",
    }
    values.update(overrides)
    return Settings(_env_file=None, environment="test", **values)


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _entry(**overrides) -> RequestLogEntry:
    values = {
        "request_id": "req-0000000000000001",
        "kind": "generation",
        "occurred_at": NOW,
        "auth_role": "user",
        "selected_provider": "fake",
        "provider": "fake",
        "model": "fake-small",
        "duration_ms": 10.0,
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
        "cost_usd": Decimal("0.000010"),
        "retry_count": 0,
        "fallback_used": False,
        "providers_tried": ("fake",),
        "status": "success",
        "http_status": 200,
    }
    values.update(overrides)
    return RequestLogEntry(**values)


def _tracked_entries() -> list[RequestLogEntry]:
    return [
        _entry(
            request_id="req-tracked-01",
            occurred_at=NOW - timedelta(minutes=6),
            duration_ms=10.0,
        ),
        _entry(
            request_id="req-tracked-02",
            occurred_at=NOW - timedelta(minutes=5),
            duration_ms=20.0,
            prompt_tokens=4,
            completion_tokens=6,
            total_tokens=10,
            cost_usd=Decimal("0.000020"),
            retry_count=1,
        ),
        _entry(
            request_id="req-tracked-03",
            occurred_at=NOW - timedelta(minutes=4),
            selected_provider="openai",
            provider="openai",
            model="gpt-4o-mini",
            duration_ms=30.0,
            prompt_tokens=6,
            completion_tokens=9,
            total_tokens=15,
            cost_usd=Decimal("0.000030"),
            retry_count=2,
            fallback_used=True,
            fallback_reason="provider_timeout",
            providers_tried=("openai", "fake"),
            status="error",
            error_code="provider_timeout",
            http_status=504,
        ),
        _entry(
            request_id="req-tracked-04",
            kind="fault_report",
            occurred_at=NOW - timedelta(minutes=3),
            duration_ms=40.0,
            prompt_tokens=8,
            completion_tokens=12,
            total_tokens=20,
            cost_usd=Decimal("0.000040"),
            retry_count=3,
            fallback_used=True,
            fallback_reason="invalid_response",
            providers_tried=("fake", "fake"),
            status="degraded",
            extraction="deterministic",
            extraction_reason="invalid_response",
            missing_field_count=2,
        ),
        _entry(
            request_id="req-tracked-05",
            kind="fault_report",
            occurred_at=NOW - timedelta(minutes=2),
            provider=None,
            selected_provider="fake",
            duration_ms=50.0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=Decimal("0.000000"),
            providers_tried=(),
            status="degraded",
            extraction="deterministic",
        ),
        _entry(
            request_id="req-tracked-06",
            occurred_at=NOW - timedelta(minutes=1),
            provider=None,
            duration_ms=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=Decimal("0.000000"),
            providers_tried=(),
            status="error",
            error_code="request_validation_failed",
            http_status=422,
        ),
    ]


@pytest.fixture
async def database() -> AsyncIterator[DatabaseManager]:
    manager = DatabaseManager(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_size=5,
        max_overflow=10,
        auto_create=True,
    )
    await manager.initialize()
    try:
        yield manager
    finally:
        await manager.dispose()


async def _seed(
    database: DatabaseManager, entries: list[RequestLogEntry]
) -> None:
    repository = RequestLogRepository(database.session_factory)
    for entry in entries:
        await repository.add(entry)


def _service(
    database: DatabaseManager,
    *,
    sample_limit: int = 10,
) -> MonitoringService:
    return MonitoringService(
        MonitoringRepository(database.session_factory),
        timeout_seconds=5.0,
        sample_limit=sample_limit,
        clock=lambda: NOW,
    )


async def test_aggregation_reports_latency_cost_and_outcomes(
    database: DatabaseManager,
) -> None:
    await _seed(database, _tracked_entries())
    report = await _service(database).summary(window="24h")

    assert report.window == "24h"
    assert report.window_start == NOW - timedelta(hours=24)
    assert report.window_end == NOW
    assert report.latency_sample_limit == 10

    totals = report.totals
    assert totals.requests == 6
    assert totals.accepted == 4
    assert totals.successful == 2
    assert totals.degraded == 2
    assert totals.errors == 2
    assert totals.provider_requests == 4
    assert totals.provider_failures == 1
    assert totals.fallback_requests == 2
    assert totals.retry_count == 6
    assert totals.prompt_tokens == 20
    assert totals.completion_tokens == 30
    assert totals.total_tokens == 50
    assert totals.cost_usd == Decimal("0.000100")
    assert totals.latency.average_ms == 25.0
    assert totals.latency.p50_ms == 20.0
    assert totals.latency.p95_ms == 50.0
    assert totals.latency.min_ms == 0.0
    assert totals.latency.max_ms == 50.0
    assert totals.latency.sample_size == 6
    assert totals.latency.sample_truncated is False

    kinds = {metrics.kind: metrics for metrics in report.by_kind}
    assert set(kinds) == {"generation", "fault_report"}
    generation = kinds["generation"]
    assert generation.requests == 4
    assert generation.accepted == 2
    assert generation.errors == 2
    assert generation.provider_requests == 3
    assert generation.provider_failures == 1
    assert generation.fallback_requests == 1
    assert generation.retry_count == 3
    assert generation.total_tokens == 30
    assert generation.cost_usd == Decimal("0.000060")
    assert generation.latency.average_ms == 15.0
    assert generation.latency.p50_ms == 10.0
    assert generation.latency.p95_ms == 30.0

    fault = kinds["fault_report"]
    assert fault.requests == 2
    assert fault.accepted == 2
    assert fault.successful == 0
    assert fault.degraded == 2
    assert fault.errors == 0
    assert fault.provider_requests == 1
    assert fault.fallback_requests == 1
    assert fault.cost_usd == Decimal("0.000040")
    assert fault.latency.p50_ms == 40.0
    assert fault.latency.p95_ms == 50.0

    providers = {metrics.provider: metrics for metrics in report.by_provider}
    assert set(providers) == {"fake", "openai"}
    fake = providers["fake"]
    assert fake.requests == 3
    assert fake.accepted == 3
    assert fake.degraded == 1
    assert fake.errors == 0
    assert fake.fallback_requests == 1
    assert fake.retry_count == 4
    assert fake.total_tokens == 35
    assert fake.cost_usd == Decimal("0.000070")
    assert fake.latency.average_ms == 23.333
    assert fake.latency.p50_ms == 20.0
    assert fake.latency.p95_ms == 40.0

    openai = providers["openai"]
    assert openai.requests == 1
    assert openai.accepted == 0
    assert openai.errors == 1
    assert openai.provider_failures == 1
    assert openai.latency.p50_ms == 30.0

    summary = performance_summary(totals)
    assert summary.accepted_rate == pytest.approx(0.666667, rel=1e-3)
    assert summary.success_rate == pytest.approx(0.333333, rel=1e-3)
    assert summary.error_rate == pytest.approx(0.333333, rel=1e-3)
    assert summary.provider_failure_rate == 0.25
    assert summary.fallback_rate == pytest.approx(0.333333, rel=1e-3)
    assert summary.cost_usd == pytest.approx(0.0001)
    assert summary.cost_per_request_usd == pytest.approx(
        0.000016667, rel=1e-3
    )
    assert summary.cost_per_accepted_result_usd == pytest.approx(0.000025)


async def test_window_excludes_older_records(database: DatabaseManager) -> None:
    await _seed(
        database,
        [
            _entry(request_id="req-current", occurred_at=NOW - timedelta(hours=1)),
            _entry(request_id="req-old", occurred_at=NOW - timedelta(hours=25)),
        ],
    )
    service = _service(database)

    last_day = await service.summary(window="24h")
    last_week = await service.summary(window="7d")

    assert last_day.totals.requests == 1
    assert last_week.totals.requests == 2


async def test_summary_filters_by_kind_and_provider(
    database: DatabaseManager,
) -> None:
    await _seed(database, _tracked_entries())
    report = await _service(database).summary(
        window="24h",
        kind="generation",
        provider="fake",
    )

    assert report.totals.requests == 2
    assert report.totals.accepted == 2
    assert report.totals.errors == 0
    assert report.totals.cost_usd == Decimal("0.000030")
    assert [metrics.provider for metrics in report.by_provider] == ["fake"]
    assert [metrics.kind for metrics in report.by_kind] == ["generation"]


async def test_empty_window_returns_zero_report(
    database: DatabaseManager,
) -> None:
    report = await _service(database).summary(window="1h")

    totals = report.totals
    assert totals.requests == 0
    assert totals.accepted == 0
    assert totals.errors == 0
    assert totals.cost_usd == Decimal("0")
    assert totals.latency.average_ms == 0.0
    assert totals.latency.p50_ms is None
    assert totals.latency.p95_ms is None
    assert totals.latency.min_ms is None
    assert totals.latency.max_ms is None
    assert totals.latency.sample_size == 0
    assert totals.latency.sample_truncated is False
    assert report.by_kind == ()
    assert report.by_provider == ()


async def test_latency_percentiles_use_a_bounded_latest_sample(
    database: DatabaseManager,
) -> None:
    entries = [
        _entry(
            request_id=f"req-sample-{index:02d}",
            occurred_at=NOW - timedelta(minutes=index),
            duration_ms=float(index + 1),
        )
        for index in range(12)
    ]
    await _seed(database, entries)
    report = await _service(database, sample_limit=10).summary(window="24h")

    latency = report.totals.latency
    assert report.totals.requests == 12
    assert latency.average_ms == 6.5
    assert latency.sample_size == 10
    assert latency.sample_truncated is True
    assert latency.p50_ms == 5.0
    assert latency.p95_ms == 10.0
    assert latency.min_ms == 1.0
    assert latency.max_ms == 12.0


async def test_monitoring_requires_persistence_and_bounds_queries() -> None:
    disabled = MonitoringService(
        None,
        timeout_seconds=0.1,
        sample_limit=10,
    )
    assert disabled.enabled is False
    with pytest.raises(MonitoringUnavailableError):
        await disabled.summary(window="24h")

    class SlowRepository:
        async def aggregate(self, **_: object) -> None:
            await asyncio.sleep(1)

    slow = MonitoringService(
        SlowRepository(),  # type: ignore[arg-type]
        timeout_seconds=0.01,
        sample_limit=10,
    )
    with pytest.raises(MonitoringUnavailableError):
        await slow.summary(window="24h")


async def test_missing_table_is_reported_as_monitoring_unavailable() -> None:
    manager = DatabaseManager(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_size=5,
        max_overflow=10,
        auto_create=False,
    )
    service = MonitoringService(
        MonitoringRepository(manager.session_factory),
        timeout_seconds=1.0,
        sample_limit=10,
    )
    try:
        with pytest.raises(MonitoringUnavailableError):
            await service.summary(window="24h")
    finally:
        await manager.dispose()


async def test_request_log_observer_runs_without_persistence() -> None:
    observed: list[RequestLogEntry] = []

    def observer(entry: RequestLogEntry) -> None:
        observed.append(entry)

    entry = _entry()
    disabled = RequestLogService(
        None,
        timeout_seconds=0.1,
        observer=observer,
    )
    assert await disabled.record(entry) is False
    assert observed == [entry]

    def broken(_: RequestLogEntry) -> None:
        raise RuntimeError("metrics backend failed")

    safe = RequestLogService(
        None,
        timeout_seconds=0.1,
        observer=broken,
    )
    assert await safe.record(entry) is False


def test_metrics_collector_uses_bounded_labels_and_no_request_content() -> None:
    collector = MetricsCollector()
    collector.observe(
        _entry(
            request_id="req-secret-request-id",
            provider="fake",
            duration_ms=125.0,
            cost_usd=Decimal("0.000050"),
            retry_count=2,
            fallback_used=True,
            fallback_reason="provider_timeout",
        )
    )
    collector.observe(
        _entry(
            request_id="req-secret-request-id-2",
            provider="unknown-client-name",
            duration_ms=0.0,
            cost_usd=Decimal("0"),
            status="error",
            error_code="provider_not_found",
            http_status=404,
        )
    )

    text = collector.render().decode("utf-8")
    assert "ai_adapter_requests_total" in text
    assert 'kind="generation"' in text
    assert 'provider="fake"' in text
    assert 'status="success"' in text
    assert 'status="error"' in text
    assert 'provider="unconfigured"' in text
    assert "ai_adapter_request_duration_seconds_count" in text
    assert "ai_adapter_cost_usd_total" in text
    assert 'token_type="total"' in text
    assert "ai_adapter_retries_total" in text
    assert 'reason="provider_timeout"' in text
    assert "ai_adapter_accepted_results_total" in text
    assert "ai_adapter_errors_total" in text
    assert "ai_adapter_provider_failures_total" in text
    assert "req-secret-request-id" not in text
    assert "unknown-client-name" not in text


def test_metrics_endpoint_works_without_database_and_hides_prompts() -> None:
    with _client(_settings(database_enabled=False)) as client:
        generated = client.post(
            "/api/v1/generate",
            json={
                "messages": [
                    {"role": "user", "content": "super-secret-prompt"}
                ]
            },
        )
        missing = client.post(
            "/api/v1/generate",
            json={
                "provider": "missing",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        response = client.get("/api/v1/monitoring/metrics")
        summary = client.get("/api/v1/monitoring/summary")

    assert generated.status_code == 200
    assert missing.status_code == 404
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=")
    text = response.text
    assert "ai_adapter_requests_total" in text
    assert 'provider="fake"' in text
    assert 'status="success"' in text
    assert 'provider="unconfigured"' in text
    assert 'error_code="provider_not_found"' in text
    assert "ai_adapter_accepted_results_total" in text
    assert "super-secret-prompt" not in text
    assert "/api/v1/generate" not in text
    assert summary.status_code == 503
    assert summary.json()["error"]["code"] == "monitoring_unavailable"


def test_summary_and_metrics_require_an_administrator() -> None:
    settings = _settings(
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
        security_rate_limit_requests=50,
    )
    with _client(settings) as client:
        for path in (
            "/api/v1/monitoring/summary",
            "/api/v1/monitoring/metrics",
        ):
            missing = client.get(path)
            forbidden = client.get(path, headers=_headers(USER_KEY))
            allowed = client.get(path, headers=_headers(ADMIN_KEY))
            assert missing.status_code == 401
            assert forbidden.status_code == 403
            assert allowed.status_code == 200


def test_summary_reports_live_recorded_requests() -> None:
    with _client(_settings()) as client:
        generated = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        fault = client.post(
            "/api/v1/fault-reports/summarize",
            json={"report": "Pump 7 overheated and stopped for 20 minutes."},
        )
        response = client.get("/api/v1/monitoring/summary")

    assert generated.status_code == 200
    assert fault.status_code == 200
    assert fault.json()["extraction"] == "deterministic"
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["requests"] == 2
    assert body["totals"]["accepted"] == 2
    assert body["totals"]["successful"] == 1
    assert body["totals"]["degraded"] == 1
    assert body["totals"]["errors"] == 0
    assert body["totals"]["cost_usd"] == 0.0
    assert body["totals"]["latency"]["sample_size"] == 2
    assert {item["kind"] for item in body["by_kind"]} == {
        "generation",
        "fault_report",
    }
    assert sum(item["requests"] for item in body["by_provider"]) == 2


def test_summary_rates_and_cost_ratios() -> None:
    settings = _settings()
    with _client(settings) as client:
        for index in range(3):
            client.post(
                "/api/v1/generate",
                json={
                    "messages": [
                        {"role": "user", "content": f"request {index}"}
                    ]
                },
            )
        client.post(
            "/api/v1/fault-reports/summarize",
            json={"report": "Compressor C2 tripped after a pressure spike."},
        )
        body = client.get("/api/v1/monitoring/summary").json()

    totals = body["totals"]
    assert totals["requests"] == 4
    assert totals["accepted"] == 4
    assert totals["accepted_rate"] == 1.0
    assert totals["success_rate"] == 0.75
    assert totals["degraded_rate"] == 0.25
    assert totals["error_rate"] == 0.0
    assert totals["provider_failure_rate"] == 0.0
    assert totals["fallback_rate"] == 0.0
    assert totals["cost_per_request_usd"] == 0.0
    assert totals["cost_per_accepted_result_usd"] == 0.0


def test_summary_validates_window_and_provider_filter() -> None:
    with _client(_settings()) as client:
        invalid_window = client.get(
            "/api/v1/monitoring/summary", params={"window": "2h"}
        )
        invalid_provider = client.get(
            "/api/v1/monitoring/summary",
            params={"provider": "Not A Provider"},
        )

    assert invalid_window.status_code == 422
    assert invalid_provider.status_code == 422


def test_monitoring_settings_are_bounded() -> None:
    with pytest.raises(ValidationError):
        _settings(monitoring_latency_sample_limit=9)
    with pytest.raises(ValidationError):
        _settings(monitoring_latency_sample_limit=100_001)
    with pytest.raises(ValidationError):
        _settings(monitoring_query_timeout_seconds=0.0)

    settings = _settings(
        monitoring_latency_sample_limit=25,
        monitoring_query_timeout_seconds=2.5,
    )
    assert settings.monitoring_latency_sample_limit == 25
    assert settings.monitoring_query_timeout_seconds == 2.5
