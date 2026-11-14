"""Stage H: deterministic end-to-end fault-injection matrix.

Every fault is injected by a test-only provider. Production code has no
fault-injection switch. The tests exercise the real application factory,
authentication, reliability chain, budget hook, request logging, and SQLite
persistence for both business endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import pytest
from app.budget.pricing import PricingRates
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
)
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from fastapi.testclient import TestClient

pytestmark = pytest.mark.fault_matrix

USER_KEY = "matrix-user-key-0123456789abcdef"
ADMIN_KEY = "matrix-admin-key-0123456789abcdef"
PROMPT_MARKER = "MATRIX-CONFIDENTIAL-PROMPT"
REPORT_MARKER = "MATRIX-CONFIDENTIAL-REPORT"
ERROR_SECRET = "sk-matrix-secret-0123456789"

REPORT = """Machine: Press 4
Fault description: Bearing seized after abnormal vibration
Temperature: 80 C
Downtime: 10 minutes
Action taken: Replaced the bearing
Severity: high"""

VALID_SUMMARY = {
    "machine": "Conveyor 3",
    "fault_description": "Bearing seized after abnormal vibration",
    "temperature": 87.0,
    "temperature_unit": "C",
    "downtime": "2 hours",
    "action_taken": "Replaced the bearing and realigned the belt",
    "severity": "high",
}
VALID_SUMMARY_JSON = json.dumps(VALID_SUMMARY)

FaultMode = Literal[
    "timeout",
    "rate_limit",
    "server_error",
    "unavailable",
    "invalid_response",
    "wrong_identity",
    "authentication",
    "invalid_request",
]


@dataclass(frozen=True)
class FaultCase:
    mode: FaultMode
    error_code: str
    http_status: int
    retryable: bool


RETRYABLE_FAULTS = (
    FaultCase("timeout", "provider_timeout", 504, True),
    FaultCase("rate_limit", "provider_rate_limit", 429, True),
    FaultCase("server_error", "provider_server_error", 502, True),
    FaultCase("unavailable", "provider_unavailable", 503, True),
    FaultCase("invalid_response", "provider_invalid_response", 502, True),
    FaultCase("wrong_identity", "provider_invalid_response", 502, True),
)

TERMINAL_FAULTS = (
    FaultCase("authentication", "provider_authentication_failed", 502, False),
    FaultCase("invalid_request", "provider_invalid_request", 400, False),
)

_FAULT_ERRORS: dict[str, type[Exception]] = {
    "rate_limit": ProviderRateLimitError,
    "server_error": ProviderServerError,
    "unavailable": ProviderUnavailableError,
    "invalid_response": ProviderInvalidResponseError,
    "authentication": ProviderAuthenticationError,
    "invalid_request": ProviderInvalidRequestError,
}


class FaultProvider(FakeProvider):
    """Test-only adapter that injects one deterministic failure mode."""

    def __init__(
        self,
        *,
        fault: FaultMode | None = None,
        success_content: str | None = None,
        error_message: str = "injected upstream fault",
        hang_seconds: float = 5.0,
    ) -> None:
        super().__init__(
            name="primary",
            display_name="Fault-Injection Primary",
            models=("primary-small",),
            default_model="primary-small",
        )
        self._fault = fault
        self._success_content = success_content
        self._error_message = error_message
        self._hang_seconds = hang_seconds
        self.calls = 0
        self.models_requested: list[str] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        self.models_requested.append(request.model)

        if self._fault == "timeout":
            await asyncio.sleep(self._hang_seconds)
            raise AssertionError("injected timeout was not enforced")

        if self._fault == "wrong_identity":
            result = await self._success(request)
            return result.model_copy(update={"provider": "impostor"})

        error_type = _FAULT_ERRORS.get(self._fault or "")
        if error_type is not None:
            raise error_type(self._error_message, provider=self.name)

        return await self._success(request)

    async def _success(self, request: GenerationRequest) -> GenerationResult:
        if self._success_content is None:
            return await super().generate(request)
        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=self._success_content,
            usage=TokenUsage(
                prompt_tokens=8,
                completion_tokens=6,
                total_tokens=14,
            ),
            finish_reason="stop",
            latency_ms=0.1,
        )


def _settings(
    *,
    fallback: bool,
    max_attempts: int = 3,
    timeout: float = 0.03,
    circuit_threshold: int = 20,
    rate_limit_requests: int = 0,
) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
        default_provider="primary",
        security_require_auth=True,
        security_api_keys=USER_KEY,
        security_admin_api_keys=ADMIN_KEY,
        security_rate_limit_requests=rate_limit_requests,
        security_rate_limit_window_seconds=60.0,
        reliability_secondary_provider="",
        reliability_fallback_provider="fake" if fallback else "",
        reliability_max_attempts=max_attempts,
        reliability_backoff_base_seconds=0.0,
        reliability_backoff_max_seconds=0.0,
        reliability_jitter_seconds=0.0,
        reliability_timeout_seconds=timeout,
        reliability_circuit_failure_threshold=circuit_threshold,
        reliability_circuit_recovery_seconds=60.0,
        budget_enforcement_enabled=False,
        budget_provider_pricing={
            "primary": PricingRates.free(),
            "fake": PricingRates.free(),
        },
        database_enabled=True,
        database_url="sqlite+aiosqlite:///:memory:",
        database_auto_create=True,
    )


@contextmanager
def _running(provider: FaultProvider, settings: Settings):
    registry = ProviderRegistry()
    registry.register(provider)
    if settings.reliability_fallback_provider:
        registry.register(FakeProvider(name="fake"))
    app = create_app(settings, registry=registry)
    with TestClient(app) as client:
        yield client, app


def _user_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {USER_KEY}",
        "X-Request-ID": request_id,
    }


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def _generate(
    client: TestClient,
    request_id: str,
    *,
    prompt: str = "matrix request",
    provider: str | None = None,
):
    body: dict = {
        "messages": [{"role": "user", "content": prompt}],
    }
    if provider is not None:
        body["provider"] = provider
    return client.post(
        "/api/v1/generate",
        headers=_user_headers(request_id),
        json=body,
    )


def _summarize(
    client: TestClient,
    request_id: str,
    *,
    report: str = REPORT,
    provider: str | None = None,
):
    body: dict = {"report": report}
    if provider is not None:
        body["provider"] = provider
    return client.post(
        "/api/v1/fault-reports/summarize",
        headers=_user_headers(request_id),
        json=body,
    )


def _history(client: TestClient) -> list[dict]:
    response = client.get(
        "/api/v1/requests",
        headers=_admin_headers(),
        params={"limit": 200},
    )
    assert response.status_code == 200
    return response.json()["items"]


def _row(client: TestClient, request_id: str) -> dict:
    rows = [item for item in _history(client) if item["request_id"] == request_id]
    assert len(rows) == 1, f"expected one request-log row for {request_id}"
    return rows[0]


def test_matrix_manifest_covers_every_fault_class() -> None:
    assert {case.mode for case in RETRYABLE_FAULTS} == {
        "timeout",
        "rate_limit",
        "server_error",
        "unavailable",
        "invalid_response",
        "wrong_identity",
    }
    assert all(case.retryable for case in RETRYABLE_FAULTS)
    assert {case.mode for case in TERMINAL_FAULTS} == {
        "authentication",
        "invalid_request",
    }
    assert all(not case.retryable for case in TERMINAL_FAULTS)


@pytest.mark.parametrize(
    "case",
    RETRYABLE_FAULTS,
    ids=[case.mode for case in RETRYABLE_FAULTS],
)
def test_generation_exhaustion_returns_normalized_failure(case: FaultCase) -> None:
    provider = FaultProvider(fault=case.mode)
    request_id = f"matrix-generation-{case.mode}"

    with _running(provider, _settings(fallback=False)) as (client, _):
        response = _generate(client, request_id)

        assert response.status_code == case.http_status
        assert response.headers["X-Request-ID"] == request_id
        body = response.json()
        assert body["request_id"] == request_id
        assert body["error"]["code"] == case.error_code
        assert body["error"]["retryable"] is case.retryable
        assert provider.calls == 3

        row = _row(client, request_id)
        assert row["kind"] == "generation"
        assert row["status"] == "error"
        assert row["error_code"] == case.error_code
        assert row["http_status"] == case.http_status
        assert row["retry_count"] == 2
        assert row["fallback_used"] is False
        assert row["providers_tried"] == ["primary"]
        assert row["selected_provider"] == "primary"
        assert row["provider"] == "primary"
        assert row["auth_role"] == "user"


@pytest.mark.parametrize(
    "case",
    RETRYABLE_FAULTS,
    ids=[case.mode for case in RETRYABLE_FAULTS],
)
def test_generation_fallback_recovers_from_provider_fault(case: FaultCase) -> None:
    provider = FaultProvider(fault=case.mode)
    request_id = f"matrix-fallback-{case.mode}"

    with _running(provider, _settings(fallback=True)) as (client, _):
        response = _generate(client, request_id)

        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "fake"
        assert body["fallback_used"] is True
        assert body["fallback_reason"] == case.error_code
        assert body["retry_count"] == 2
        assert body["providers_tried"] == ["primary", "fake"]
        assert provider.calls == 3

        row = _row(client, request_id)
        assert row["status"] == "success"
        assert row["provider"] == "fake"
        assert row["fallback_used"] is True
        assert row["fallback_reason"] == case.error_code
        assert row["retry_count"] == 2
        assert row["providers_tried"] == ["primary", "fake"]


@pytest.mark.parametrize(
    "case",
    RETRYABLE_FAULTS,
    ids=[case.mode for case in RETRYABLE_FAULTS],
)
def test_fault_report_degrades_to_deterministic_extraction(case: FaultCase) -> None:
    provider = FaultProvider(fault=case.mode)
    request_id = f"matrix-report-{case.mode}"

    with _running(provider, _settings(fallback=False)) as (client, _):
        response = _summarize(client, request_id)

        assert response.status_code == 200
        body = response.json()
        assert body["extraction"] == "deterministic"
        assert body["extraction_reason"] == case.error_code
        assert body["provider"] is None
        assert body["model"] is None
        assert body["fallback_used"] is False
        assert body["retry_count"] == 2
        assert body["providers_tried"] == ["primary"]
        assert body["summary"]["machine"] == "Press 4"
        assert body["total_tokens"] == 0
        assert body["cost_usd"] == 0.0
        assert provider.calls == 3

        row = _row(client, request_id)
        assert row["kind"] == "fault_report"
        assert row["status"] == "degraded"
        assert row["http_status"] == 200
        assert row["error_code"] is None
        assert row["provider"] is None
        assert row["extraction"] == "deterministic"
        assert row["extraction_reason"] == case.error_code
        assert row["retry_count"] == 2
        assert row["providers_tried"] == ["primary"]


def test_client_errors_are_not_masked_by_fallback_or_extraction() -> None:
    provider = FaultProvider(fault="invalid_request")
    settings = _settings(fallback=True)

    with _running(provider, settings) as (client, _):
        generation = _generate(client, "matrix-terminal-generation")
        summary = _summarize(client, "matrix-terminal-report")

        assert generation.status_code == 400
        assert generation.json()["error"]["code"] == "provider_invalid_request"
        assert summary.status_code == 400
        assert summary.json()["error"]["code"] == "provider_invalid_request"
        assert provider.calls == 2

        generation_row = _row(client, "matrix-terminal-generation")
        summary_row = _row(client, "matrix-terminal-report")
        for row in (generation_row, summary_row):
            assert row["status"] == "error"
            assert row["error_code"] == "provider_invalid_request"
            assert row["http_status"] == 400
            assert row["retry_count"] == 0
            assert row["fallback_used"] is False


def test_unknown_provider_is_not_masked() -> None:
    provider = FaultProvider()

    with _running(provider, _settings(fallback=True)) as (client, _):
        generation = _generate(
            client,
            "matrix-unknown-generation",
            provider="ghost",
        )
        summary = _summarize(
            client,
            "matrix-unknown-report",
            provider="ghost",
        )

        assert generation.status_code == 404
        assert summary.status_code == 404
        assert generation.json()["error"]["code"] == "provider_not_found"
        assert summary.json()["error"]["code"] == "provider_not_found"
        assert provider.calls == 0

        generation_row = _row(client, "matrix-unknown-generation")
        summary_row = _row(client, "matrix-unknown-report")
        for row in (generation_row, summary_row):
            assert row["status"] == "error"
            assert row["error_code"] == "provider_not_found"
            assert row["http_status"] == 404
            assert row["selected_provider"] == "ghost"
            assert row["provider"] == "ghost"


def test_provider_authentication_faults_follow_the_reliability_policy() -> None:
    provider = FaultProvider(fault="authentication")

    with _running(provider, _settings(fallback=True)) as (client, _):
        response = _generate(client, "matrix-auth-generation")

        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "fake"
        assert body["fallback_used"] is True
        assert body["fallback_reason"] == "provider_authentication_failed"
        assert body["retry_count"] == 0
        assert provider.calls == 1

    provider = FaultProvider(fault="authentication")
    with _running(provider, _settings(fallback=False)) as (client, _):
        response = _summarize(client, "matrix-auth-report")

        assert response.status_code == 200
        body = response.json()
        assert body["extraction"] == "deterministic"
        assert body["extraction_reason"] == "provider_authentication_failed"
        assert body["retry_count"] == 0
        assert provider.calls == 1


@pytest.mark.parametrize(
    ("content", "extraction", "reason"),
    [
        ("not-json-output", "deterministic", "ai_invalid_json"),
        ('{"severity": "urgent"}', "deterministic", "ai_invalid_schema"),
        ("{}", "deterministic", "ai_empty_summary"),
        (VALID_SUMMARY_JSON, "provider", None),
    ],
    ids=["invalid_json", "invalid_schema", "empty_summary", "valid_control"],
)
def test_provider_output_faults_have_explicit_extraction_outcomes(
    content: str,
    extraction: str,
    reason: str | None,
) -> None:
    provider = FaultProvider(success_content=content)
    request_id = f"matrix-output-{reason or 'valid'}"

    with _running(provider, _settings(fallback=False, max_attempts=1)) as (
        client,
        _,
    ):
        response = _summarize(client, request_id)

        assert response.status_code == 200
        body = response.json()
        assert body["extraction"] == extraction
        assert body["extraction_reason"] == reason
        assert body["retry_count"] == 0
        assert provider.calls == 1

        row = _row(client, request_id)
        assert row["extraction"] == extraction
        assert row["extraction_reason"] == reason
        assert row["status"] == ("success" if extraction == "provider" else "degraded")
        assert row["http_status"] == 200

        if extraction == "provider":
            assert body["provider"] == "primary"
            assert body["summary"]["machine"] == "Conveyor 3"
            assert body["total_tokens"] == 14
        else:
            assert body["provider"] == "primary"
            assert body["summary"]["machine"] == "Press 4"


def test_timeout_fault_is_bounded_and_cancelled() -> None:
    provider = FaultProvider(fault="timeout", hang_seconds=5.0)
    settings = _settings(fallback=True, max_attempts=2, timeout=0.03)

    with _running(provider, settings) as (client, _):
        started = time.perf_counter()
        response = _generate(client, "matrix-timeout-bound")
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        assert elapsed < 1.5
        assert provider.calls == 2
        assert response.json()["fallback_reason"] == "provider_timeout"
        assert response.json()["retry_count"] == 1


def test_circuit_breaker_opens_and_stops_attempts() -> None:
    provider = FaultProvider(fault="unavailable")
    settings = _settings(
        fallback=True,
        max_attempts=2,
        circuit_threshold=2,
    )

    with _running(provider, settings) as (client, app):
        first = _generate(client, "matrix-circuit-first")
        assert first.status_code == 200
        assert first.json()["fallback_reason"] == "provider_unavailable"
        assert first.json()["retry_count"] == 1
        assert provider.calls == 2

        snapshot = app.state.provider_router.circuit_snapshot("primary")
        assert snapshot.state == "open"
        assert snapshot.failure_count == 2

        second = _generate(client, "matrix-circuit-second")
        assert second.status_code == 200
        assert second.json()["fallback_reason"] == "provider_circuit_open"
        assert second.json()["retry_count"] == 0
        assert provider.calls == 2

        second_row = _row(client, "matrix-circuit-second")
        assert second_row["fallback_used"] is True
        assert second_row["fallback_reason"] == "provider_circuit_open"


def test_success_control_paths_remain_healthy() -> None:
    provider = FaultProvider(success_content=VALID_SUMMARY_JSON)

    with _running(provider, _settings(fallback=False)) as (client, _):
        generation = _generate(client, "matrix-control-generation")
        summary = _summarize(client, "matrix-control-report")

        assert generation.status_code == 200
        assert generation.json()["provider"] == "primary"
        assert generation.json()["fallback_used"] is False
        assert generation.json()["retry_count"] == 0

        assert summary.status_code == 200
        body = summary.json()
        assert body["extraction"] == "provider"
        assert body["extraction_reason"] is None
        assert body["summary"]["machine"] == "Conveyor 3"
        assert provider.calls == 2

        assert _row(client, "matrix-control-generation")["status"] == "success"
        assert _row(client, "matrix-control-report")["status"] == "success"


def test_fault_metadata_is_persisted_without_content_or_secret_leaks(
    caplog,
) -> None:
    caplog.set_level(logging.DEBUG)
    provider = FaultProvider(
        fault="server_error",
        error_message=(
            f"upstream rejected Authorization: Bearer {ERROR_SECRET}"
        ),
    )

    with _running(provider, _settings(fallback=False, max_attempts=1)) as (
        client,
        _,
    ):
        generation = _generate(
            client,
            "matrix-leak-generation",
            prompt=f"{PROMPT_MARKER} hello",
        )
        summary = _summarize(
            client,
            "matrix-leak-report",
            report=f"{REPORT_MARKER}\n{REPORT}",
        )

        assert generation.status_code == 502
        assert summary.status_code == 200
        assert summary.json()["extraction"] == "deterministic"
        assert ERROR_SECRET not in generation.text
        assert ERROR_SECRET not in summary.text
        assert PROMPT_MARKER not in generation.text
        assert REPORT_MARKER not in summary.text

        rows = _history(client)
        serialized_rows = json.dumps(rows)
        assert PROMPT_MARKER not in serialized_rows
        assert REPORT_MARKER not in serialized_rows
        assert ERROR_SECRET not in serialized_rows
        assert USER_KEY not in serialized_rows
        assert "Authorization" not in serialized_rows

        logged = " ".join(str(record.__dict__) for record in caplog.records)
        assert PROMPT_MARKER not in logged
        assert REPORT_MARKER not in logged
        assert ERROR_SECRET not in logged
        assert USER_KEY not in logged
        assert "Authorization: Bearer [REDACTED]" in logged


def test_admission_faults_do_not_reach_the_provider() -> None:
    provider = FaultProvider()
    settings = _settings(fallback=False, rate_limit_requests=1)

    with _running(provider, settings) as (client, _):
        unauthenticated = client.post(
            "/api/v1/generate",
            headers={"X-Request-ID": "matrix-admission-auth"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        first = _generate(client, "matrix-admission-first")
        limited = _generate(client, "matrix-admission-limited")

        assert unauthenticated.status_code == 401
        assert first.status_code == 200
        assert limited.status_code == 429
        assert limited.headers["Retry-After"]
        assert provider.calls == 1

        rows = {
            item["request_id"]: item
            for item in _history(client)
            if item["request_id"]
            in {"matrix-admission-auth", "matrix-admission-limited"}
        }
        assert rows["matrix-admission-auth"]["error_code"] == "authentication_required"
        assert rows["matrix-admission-auth"]["http_status"] == 401
        assert rows["matrix-admission-limited"]["error_code"] == "rate_limit_exceeded"
        assert rows["matrix-admission-limited"]["http_status"] == 429
