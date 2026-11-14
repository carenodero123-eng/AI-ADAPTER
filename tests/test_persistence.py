"""Stage G persistence, request logging, and request-history tests."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.core.config import Settings
from app.database.engine import DatabaseManager
from app.database.errors import PersistenceUnavailableError
from app.database.records import RequestLogEntry
from app.database.repository import RequestLogRepository
from app.database.service import RequestLogService
from app.faults.models import FaultSummary
from app.main import create_app
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

USER_KEY = "user-key-0123456789abcdef"
ADMIN_KEY = "admin-key-0123456789abcdef"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides) -> Settings:
    values = {
        "database_enabled": True,
        "database_url": "sqlite+aiosqlite:///:memory:",
        "database_auto_create": True,
        "security_require_auth": False,
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
        "log_level": "WARNING",
        "log_format": "console",
    }
    values.update(overrides)
    return Settings(_env_file=None, environment="test", **values)


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _body(content: str = "hello") -> dict:
    return {"messages": [{"role": "user", "content": content}]}


def _entry(**overrides) -> RequestLogEntry:
    values = {
        "request_id": "req-0123456789abcdef",
        "kind": "generation",
        "occurred_at": datetime.now(UTC),
        "auth_role": "user",
        "selected_provider": "fake",
        "provider": "fake",
        "model": "fake-small",
        "duration_ms": 1.25,
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
        "cost_usd": Decimal("0.000010"),
        "retry_count": 1,
        "fallback_used": True,
        "fallback_reason": "provider_timeout",
        "providers_tried": ("openai", "fake"),
        "status": "degraded",
        "error_code": None,
        "http_status": 200,
        "extraction": "deterministic",
        "extraction_reason": "provider_timeout",
        "missing_field_count": 2,
    }
    values.update(overrides)
    return RequestLogEntry(**values)


class _FaultJsonProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__(
            name="stub",
            display_name="Stub Fault Provider",
            models=("stub-small",),
            default_model="stub-small",
        )

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        summary = FaultSummary(
            machine="Pump 7",
            fault_description="Bearing overheated",
            temperature=95.0,
            temperature_unit="C",
            downtime="20 minutes",
            action_taken="Line stopped and bearing replaced",
            severity="high",
        )
        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=summary.model_dump_json(),
            usage=TokenUsage(
                prompt_tokens=11,
                completion_tokens=12,
                total_tokens=23,
            ),
            finish_reason="stop",
            latency_ms=0.1,
        )


def test_database_settings_validate_drivers_and_production_guards() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(
            _env_file=None,
            database_enabled=True,
            database_url="mysql+aiomysql://localhost/app",
        )
    with pytest.raises(ValidationError, match="PostgreSQL in production"):
        Settings(
            _env_file=None,
            environment="production",
            security_require_auth=True,
            security_api_keys=USER_KEY,
            database_enabled=True,
            database_url="sqlite+aiosqlite:///./data/prod.db",
        )
    with pytest.raises(ValidationError, match="database_auto_create"):
        Settings(
            _env_file=None,
            environment="production",
            security_require_auth=True,
            security_api_keys=USER_KEY,
            database_enabled=True,
            database_url="postgresql://db-user:secret@localhost/app",
            database_auto_create=True,
        )
    with pytest.raises(ValidationError, match="database_echo"):
        Settings(
            _env_file=None,
            environment="production",
            security_require_auth=True,
            security_api_keys=USER_KEY,
            database_enabled=True,
            database_url="postgresql://db-user:secret@localhost/app",
            database_auto_create=False,
            database_echo=True,
        )

    production = Settings(
        _env_file=None,
        environment="production",
        security_require_auth=True,
        security_api_keys=USER_KEY,
        database_enabled=True,
        database_url="postgres://db-user:secret@localhost/app",
        database_auto_create=False,
    )
    assert production.database_dsn.startswith("postgresql+asyncpg://")


def test_database_url_secret_is_not_exposed_in_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_enabled=True,
        database_url="postgresql://db-user:supersecret@localhost/app",
    )
    assert "supersecret" not in repr(settings)


@pytest.mark.asyncio
async def test_repository_persists_filters_and_orders_request_logs() -> None:
    database = DatabaseManager(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_size=5,
        max_overflow=10,
        auto_create=True,
    )
    await database.initialize()
    try:
        repository = RequestLogRepository(database.session_factory)
        now = datetime.now(UTC)
        first_id = await repository.add(
            _entry(
                request_id="request-older",
                occurred_at=now - timedelta(minutes=2),
                provider="openai",
                status="error",
                error_code="provider_timeout",
                http_status=504,
            )
        )
        await repository.add(
            _entry(
                request_id="request-newer",
                occurred_at=now - timedelta(minutes=1),
                status="success",
                fallback_used=False,
                fallback_reason=None,
                providers_tried=("fake",),
                cost_usd=Decimal("0"),
            )
        )
        await repository.add(
            _entry(
                request_id="request-fault",
                kind="fault_report",
                occurred_at=now,
                provider="stub",
                model="stub-small",
                status="degraded",
            )
        )

        entries, total = await repository.list_entries(limit=10)
        assert total == 3
        assert [entry.request_id for entry in entries] == [
            "request-fault",
            "request-newer",
            "request-older",
        ]
        assert entries[0].id >= 1
        assert entries[0].occurred_at.tzinfo is not None

        errors, error_total = await repository.list_entries(status="error")
        assert error_total == 1
        assert errors[0].error_code == "provider_timeout"
        assert errors[0].http_status == 504

        faults, fault_total = await repository.list_entries(kind="fault_report")
        assert fault_total == 1
        assert faults[0].extraction == "deterministic"
        assert faults[0].providers_tried == ("openai", "fake")

        provider_entries, provider_total = await repository.list_entries(
            provider="openai"
        )
        assert provider_total == 1
        assert provider_entries[0].request_id == "request-older"

        since_entries, since_total = await repository.list_entries(
            since=now - timedelta(minutes=1, seconds=30)
        )
        assert since_total == 2
        assert [entry.request_id for entry in since_entries] == [
            "request-fault",
            "request-newer",
        ]

        page, page_total = await repository.list_entries(limit=1, offset=1)
        assert page_total == 3
        assert [entry.request_id for entry in page] == ["request-newer"]

        stored = await repository.get(first_id)
        assert stored is not None
        assert stored.cost_usd == Decimal("0.000010")
        assert await repository.get(999_999) is None
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_request_log_service_disabled_and_failures_are_safe(caplog) -> None:
    caplog.set_level("WARNING")
    disabled = RequestLogService(None, timeout_seconds=0.1)
    assert disabled.enabled is False
    assert await disabled.record(_entry()) is False
    assert await disabled.ping() is False
    with pytest.raises(PersistenceUnavailableError):
        await disabled.list_entries()
    with pytest.raises(PersistenceUnavailableError):
        await disabled.get(1)

    class BrokenRepository:
        async def add(self, entry: RequestLogEntry) -> int:
            raise RuntimeError("database credentials rejected")

    broken = RequestLogService(BrokenRepository(), timeout_seconds=0.1)  # type: ignore[arg-type]
    assert await broken.record(_entry()) is False
    assert "database credentials rejected" not in caplog.text
    assert "RuntimeError" not in caplog.text

    class SlowRepository:
        async def add(self, entry: RequestLogEntry) -> int:
            await asyncio.sleep(1)
            return 1

    slow = RequestLogService(SlowRepository(), timeout_seconds=0.01)  # type: ignore[arg-type]
    assert await slow.record(_entry()) is False


def test_generation_success_is_persisted_with_required_fields() -> None:
    with _client(_settings()) as client:
        response = client.post("/api/v1/generate", json=_body())
        page = client.get("/api/v1/requests")

    assert response.status_code == 200
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 1
    item = body["items"][0]
    result = response.json()
    assert item["request_id"] == result["request_id"]
    assert item["kind"] == "generation"
    assert item["auth_role"] == "anonymous"
    assert item["selected_provider"] == "fake"
    assert item["provider"] == "fake"
    assert item["model"] == "fake-small"
    assert item["duration_ms"] >= 0
    assert item["prompt_tokens"] == 1
    assert item["completion_tokens"] == 2
    assert item["total_tokens"] == 3
    assert item["cost_usd"] == 0.0
    assert item["retry_count"] == 0
    assert item["fallback_used"] is False
    assert item["providers_tried"] == ["fake"]
    assert item["status"] == "success"
    assert item["http_status"] == 200
    assert item["error_code"] is None


def test_fault_report_result_is_persisted_with_extraction_metadata() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    registry.register(_FaultJsonProvider())
    settings = _settings(default_provider="stub")
    app = create_app(settings, registry=registry)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/fault-reports/summarize",
            json={
                "report": "Pump 7 bearing overheated to 95 C; line stopped for 20 minutes."
            },
        )
        page = client.get("/api/v1/requests")

    assert response.status_code == 200
    assert response.json()["extraction"] == "provider"
    item = page.json()["items"][0]
    assert item["kind"] == "fault_report"
    assert item["status"] == "success"
    assert item["selected_provider"] == "stub"
    assert item["provider"] == "stub"
    assert item["model"] == "stub-small"
    assert item["prompt_tokens"] == 11
    assert item["completion_tokens"] == 12
    assert item["total_tokens"] == 23
    assert item["extraction"] == "provider"
    assert item["extraction_reason"] is None
    assert item["missing_field_count"] == 0


def test_deterministic_fault_fallback_is_persisted_as_degraded() -> None:
    with _client(_settings()) as client:
        response = client.post(
            "/api/v1/fault-reports/summarize",
            json={"report": "Compressor C2 tripped after a pressure spike."},
        )
        page = client.get("/api/v1/requests")

    assert response.status_code == 200
    assert response.json()["extraction"] == "deterministic"
    item = page.json()["items"][0]
    assert item["kind"] == "fault_report"
    assert item["status"] == "degraded"
    assert item["extraction"] == "deterministic"
    assert item["extraction_reason"]


def test_failed_requests_are_persisted_with_safe_status_metadata() -> None:
    settings = _settings(
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
        security_rate_limit_requests=50,
    )
    with _client(settings) as client:
        missing = client.post("/api/v1/generate", json=_body())
        unknown = client.post(
            "/api/v1/generate",
            json={
                "provider": "missing",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers=_headers(USER_KEY),
        )
        malformed = client.post(
            "/api/v1/generate",
            json={"messages": []},
            headers=_headers(USER_KEY),
        )
        forbidden = client.get("/api/v1/requests", headers=_headers(USER_KEY))
        page = client.get("/api/v1/requests", headers=_headers(ADMIN_KEY))

    assert missing.status_code == 401
    assert unknown.status_code == 404
    assert malformed.status_code == 422
    assert forbidden.status_code == 403
    assert page.status_code == 200

    by_code = {
        item["error_code"]: item
        for item in page.json()["items"]
        if item["status"] == "error"
    }
    assert set(by_code) == {
        "authentication_required",
        "provider_not_found",
        "request_validation_failed",
    }
    assert by_code["authentication_required"]["auth_role"] is None
    assert by_code["authentication_required"]["http_status"] == 401
    assert by_code["provider_not_found"]["selected_provider"] == "missing"
    assert by_code["provider_not_found"]["provider"] == "missing"
    assert by_code["provider_not_found"]["http_status"] == 404
    assert by_code["request_validation_failed"]["auth_role"] == "user"
    assert by_code["request_validation_failed"]["http_status"] == 422

    rendered = json.dumps(page.json())
    assert USER_KEY not in rendered
    assert ADMIN_KEY not in rendered


def test_rate_limit_and_budget_rejections_are_persisted() -> None:
    rate_settings = _settings(
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
        security_rate_limit_requests=1,
    )
    with _client(rate_settings) as client:
        first = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(USER_KEY)
        )
        limited = client.post(
            "/api/v1/generate", json=_body(), headers=_headers(USER_KEY)
        )
        page = client.get("/api/v1/requests", headers=_headers(ADMIN_KEY))

    assert first.status_code == 200
    assert limited.status_code == 429
    items = page.json()["items"]
    assert [item["status"] for item in items] == ["error", "success"]
    assert items[0]["error_code"] == "rate_limit_exceeded"
    assert items[0]["http_status"] == 429

    budget_settings = _settings(
        budget_per_request_usd="0.000001",
        budget_assumed_completion_tokens=512,
        budget_provider_pricing={
            "fake": {
                "input_per_million_usd": "1000000",
                "output_per_million_usd": "1000000",
            }
        },
    )
    with _client(budget_settings) as client:
        rejected = client.post("/api/v1/generate", json=_body())
        page = client.get("/api/v1/requests")

    assert rejected.status_code == 402
    item = page.json()["items"][0]
    assert item["status"] == "error"
    assert item["error_code"] == "budget_exceeded"
    assert item["http_status"] == 402
    assert item["selected_provider"] == "fake"
    assert item["provider"] is None


def test_request_history_requires_admin_and_supports_filters() -> None:
    settings = _settings(
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
    )
    with _client(settings) as client:
        anonymous = client.get("/api/v1/requests")
        user = client.get("/api/v1/requests", headers=_headers(USER_KEY))
        for content in ("first", "second", "third"):
            assert (
                client.post(
                    "/api/v1/generate",
                    json=_body(content),
                    headers=_headers(ADMIN_KEY),
                ).status_code
                == 200
            )

        all_items = client.get(
            "/api/v1/requests", headers=_headers(ADMIN_KEY)
        )
        page = client.get(
            "/api/v1/requests?limit=1&offset=1", headers=_headers(ADMIN_KEY)
        )
        filtered = client.get(
            "/api/v1/requests?status=success&provider=fake&kind=generation",
            headers=_headers(ADMIN_KEY),
        )
        empty = client.get(
            "/api/v1/requests?kind=fault_report", headers=_headers(ADMIN_KEY)
        )
        mixed_timezones = client.get(
            "/api/v1/requests"
            "?since=2000-01-01T00:00:00&until=2099-01-01T00:00:00Z",
            headers=_headers(ADMIN_KEY),
        )
        invalid = client.get(
            "/api/v1/requests"
            "?since=2099-01-01T00:00:00Z&until=2000-01-01T00:00:00Z",
            headers=_headers(ADMIN_KEY),
        )
        detail = client.get(
            f"/api/v1/requests/{all_items.json()['items'][0]['id']}",
            headers=_headers(ADMIN_KEY),
        )
        missing = client.get("/api/v1/requests/999", headers=_headers(ADMIN_KEY))

    assert anonymous.status_code == 401
    assert user.status_code == 403
    assert all_items.status_code == 200
    assert all_items.json()["total"] == 3
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 1
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert filtered.json()["total"] == 3
    assert empty.json()["total"] == 0
    assert mixed_timezones.status_code == 200
    assert mixed_timezones.json()["total"] == 3
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request_filter"
    assert detail.status_code == 200
    assert detail.json()["id"] == all_items.json()["items"][0]["id"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "request_log_not_found"


def test_history_is_unavailable_when_persistence_is_disabled() -> None:
    with _client(_settings(database_enabled=False)) as client:
        response = client.get("/api/v1/requests")
        single = client.get("/api/v1/requests/1")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "persistence_unavailable"
    assert single.status_code == 503


def test_readiness_reports_database_health_and_failure() -> None:
    class UnavailablePersistence:
        enabled = True

        async def ping(self) -> bool:
            return False

    app = create_app(_settings())
    with TestClient(app) as client:
        healthy = client.get("/health/ready")
        app.state.request_log_service = UnavailablePersistence()
        unhealthy = client.get("/health/ready")

    assert healthy.status_code == 200
    assert healthy.json()["checks"]["database"] == "ok"
    assert unhealthy.status_code == 503
    assert unhealthy.json()["status"] == "not_ready"
    assert unhealthy.json()["checks"]["database"] == "unavailable"


def test_readiness_detects_missing_schema() -> None:
    with _client(_settings(database_auto_create=False)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "unavailable"


def test_persistence_failure_never_breaks_generation(monkeypatch) -> None:
    app = create_app(_settings())
    repository = app.state.request_log_service._repository
    assert repository is not None

    async def fail(_entry: RequestLogEntry) -> int:
        raise RuntimeError("storage offline")

    monkeypatch.setattr(repository, "add", fail)
    with TestClient(app) as client:
        response = client.post("/api/v1/generate", json=_body())
        page = client.get("/api/v1/requests")

    assert response.status_code == 200
    assert response.json()["provider"] == "fake"
    assert page.status_code == 200
    assert page.json()["total"] == 0


def test_prompts_credentials_and_authorization_headers_are_not_persisted() -> None:
    settings = _settings(
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
    )
    secret_prompt = "TOP-SECRET-PROMPT-CONTENT"
    with _client(settings) as client:
        response = client.post(
            "/api/v1/generate",
            json=_body(secret_prompt),
            headers=_headers(USER_KEY),
        )
        page = client.get("/api/v1/requests", headers=_headers(ADMIN_KEY))

    assert response.status_code == 200
    rendered = json.dumps(page.json())
    assert secret_prompt not in rendered
    assert USER_KEY not in rendered
    assert ADMIN_KEY not in rendered
    assert "authorization" not in rendered.lower()
    assert "bearer" not in rendered.lower()


def test_alembic_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["DATABASE_ENABLED"] = "false"

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master "
                "where type='index' and tbl_name='request_logs'"
            )
        }
    assert "request_logs" in tables
    assert "ix_request_logs_request_id" in indexes
    assert "ix_request_logs_status_occurred_at" in indexes

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database_path) as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    assert "request_logs" not in remaining
