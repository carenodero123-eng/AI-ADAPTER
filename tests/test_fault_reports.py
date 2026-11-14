"""Stage F fault-report extraction, validation, fallback, and API behavior."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from decimal import Decimal

import pytest
from app.budget.pricing import PricingRates
from app.core.config import Settings
from app.faults.extraction import extract_fault_summary
from app.faults.models import FaultSummary
from app.faults.parsing import FaultSummaryParseError, parse_fault_summary
from app.main import create_app
from app.providers.errors import ProviderUnavailableError
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import GenerationResult, TokenUsage
from fastapi.testclient import TestClient
from pydantic import ValidationError

LABELED_REPORT = """Machine: Conveyor 3
Fault description: Bearing seized after abnormal vibration
Temperature: 87 °C
Downtime: 2 hours
Action taken: Replaced the bearing and realigned the belt
Severity: Major"""

PROSE_REPORT = (
    "At 09:15 the pump 3 stopped after overheating. Production recorded "
    "45 minutes of downtime. Replaced the bearing and realigned the belt. "
    "Severity: critical"
)

UNKNOWN_REPORT = (
    "Shift handover notes were reviewed. All checks completed successfully."
)

VALID_SUMMARY = {
    "machine": "Conveyor 3",
    "fault_description": "Bearing seized after abnormal vibration",
    "temperature": 87.0,
    "temperature_unit": "C",
    "downtime": "2 hours",
    "action_taken": "Replaced the bearing and realigned the belt",
    "severity": "high",
}


class _StaticProvider(FakeProvider):
    """Returns a fixed assistant payload with deterministic usage."""

    def __init__(
        self,
        content: str,
        *,
        name: str = "json",
        models: Sequence[str] = ("json-model",),
    ) -> None:
        super().__init__(name=name, models=models)
        self._content = content
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if request.model not in self.models:
            from app.providers.errors import ProviderInvalidRequestError

            raise ProviderInvalidRequestError(
                f"Model '{request.model}' is not supported.", provider=self.name
            )
        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=self._content,
            usage=TokenUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
            latency_ms=0.1,
        )


class _FailingProvider(FakeProvider):
    def __init__(self, *, name: str = "broken") -> None:
        super().__init__(name=name)
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        raise ProviderUnavailableError("upstream unavailable", provider=self.name)


def _settings(**overrides) -> Settings:
    values = {
        "security_require_auth": False,
        "reliability_backoff_base_seconds": 0.0,
        "reliability_backoff_max_seconds": 0.0,
        "reliability_jitter_seconds": 0.0,
        "reliability_fallback_provider": "",
        "log_level": "INFO",
        "log_format": "console",
    }
    values.update(overrides)
    return Settings(_env_file=None, environment="test", **values)


def _app(*providers, default_provider: str, **overrides):
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    return create_app(
        _settings(default_provider=default_provider, **overrides),
        registry=registry,
    )


def _post(client: TestClient, report: str = LABELED_REPORT, **extra):
    payload = {"report": report, **extra}
    return client.post("/api/v1/fault-reports/summarize", json=payload)


def test_extractor_populates_every_explicit_labeled_field() -> None:
    summary = extract_fault_summary(LABELED_REPORT)

    assert summary.machine == "Conveyor 3"
    assert summary.fault_description == "Bearing seized after abnormal vibration"
    assert summary.temperature == 87.0
    assert summary.temperature_unit == "C"
    assert summary.downtime == "2 hours"
    assert summary.action_taken == "Replaced the bearing and realigned the belt"
    assert summary.severity == "high"


def test_extractor_handles_prose_reports() -> None:
    summary = extract_fault_summary(PROSE_REPORT)

    assert summary.machine == "Pump 3"
    assert summary.fault_description == (
        "At 09:15 the pump 3 stopped after overheating"
    )
    assert summary.temperature is None
    assert summary.temperature_unit is None
    assert summary.downtime == "45 minutes"
    assert summary.action_taken == "Replaced the bearing and realigned the belt"
    assert summary.severity == "critical"


def test_extractor_leaves_unknown_fields_unknown() -> None:
    summary = extract_fault_summary(UNKNOWN_REPORT)

    assert summary.model_dump() == {
        "machine": None,
        "fault_description": None,
        "temperature": None,
        "temperature_unit": None,
        "downtime": None,
        "action_taken": None,
        "severity": None,
    }


def test_extractor_treats_placeholders_as_unknown() -> None:
    summary = extract_fault_summary(
        "Machine: N/A\nFault description: Not specified\n"
        "Temperature: Unknown\nDowntime: None\nAction taken: No action\n"
        "Severity: Pending"
    )

    assert summary.machine is None
    assert summary.fault_description is None
    assert summary.temperature is None
    assert summary.downtime is None
    assert summary.action_taken is None
    assert summary.severity is None


def test_extractor_does_not_invent_partial_fields() -> None:
    summary = extract_fault_summary(
        "Machine: Pump 7\nFault description: Seal leak\nSeverity: Minor"
    )

    assert summary.machine == "Pump 7"
    assert summary.fault_description == "Seal leak"
    assert summary.severity == "low"
    assert summary.temperature is None
    assert summary.downtime is None
    assert summary.action_taken is None


def test_extractor_normalizes_temperature_units_and_durations() -> None:
    assert extract_fault_summary("Temp: 212 °F").temperature == 212.0
    assert extract_fault_summary("Temp: 212 °F").temperature_unit == "F"
    assert extract_fault_summary("Temp: 100 C").temperature_unit == "C"

    assert extract_fault_summary("Downtime: 90 minutes").downtime == "90 minutes"
    assert extract_fault_summary("Downtime: 1 hour").downtime == "1 hour"
    assert extract_fault_summary("Downtime: 2 days").downtime == "2 days"


def test_summary_model_normalizes_aliases_and_rejects_invalid_shapes() -> None:
    summary = FaultSummary(
        machine="  Conveyor 3 ",
        fault_description="  'Bearing seized.'  ",
        temperature=50.0,
        temperature_unit="fahrenheit",
        severity="Critical",
    )
    assert summary.machine == "Conveyor 3"
    assert summary.fault_description == "Bearing seized"
    assert summary.temperature_unit == "F"
    assert summary.severity == "critical"

    with pytest.raises(ValidationError):
        FaultSummary(temperature_unit="C")
    with pytest.raises(ValidationError):
        FaultSummary(severity="urgent")
    with pytest.raises(ValidationError):
        FaultSummary(unexpected="value")


def test_parser_accepts_json_fences_and_surrounding_prose() -> None:
    encoded = json.dumps(VALID_SUMMARY)

    assert parse_fault_summary(encoded).machine == "Conveyor 3"
    assert parse_fault_summary(f"```json\n{encoded}\n```").severity == "high"
    assert (
        parse_fault_summary(f"Summary follows:\n{encoded}\nEnd.").downtime
        == "2 hours"
    )


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "ai_invalid_json"),
        ("I cannot answer that.", "ai_invalid_json"),
        ("{not-json}", "ai_invalid_json"),
        ("[]", "ai_invalid_json"),
        ('{"temperature_unit": "C"}', "ai_invalid_schema"),
        ('{"machine": "Pump 7", "severity": "urgent"}', "ai_invalid_schema"),
        ('{"machine": "Pump 7", "extra": true}', "ai_invalid_schema"),
    ],
)
def test_parser_rejects_invalid_ai_content(content: str, reason: str) -> None:
    with pytest.raises(FaultSummaryParseError) as info:
        parse_fault_summary(content)
    assert info.value.reason == reason


def test_api_returns_validated_provider_summary() -> None:
    provider = _StaticProvider(json.dumps(VALID_SUMMARY))
    app = _app(provider, default_provider="json")

    with TestClient(app) as client:
        response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "provider"
    assert body["extraction_reason"] is None
    assert body["summary"]["machine"] == "Conveyor 3"
    assert body["summary"]["severity"] == "high"
    assert body["missing_fields"] == []
    assert body["selected_provider"] == "json"
    assert body["provider"] == "json"
    assert body["model"] == "json-model"
    assert body["total_tokens"] == 15
    assert body["cost_usd"] == 0.0
    assert body["retry_count"] == 0
    assert body["providers_tried"] == ["json"]


def test_api_falls_back_when_ai_json_is_invalid() -> None:
    provider = _StaticProvider("I am unable to produce JSON.")
    app = _app(provider, default_provider="json")

    with TestClient(app) as client:
        response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["extraction_reason"] == "ai_invalid_json"
    assert body["summary"]["machine"] == "Conveyor 3"
    assert body["summary"]["temperature"] == 87.0
    assert body["provider"] == "json"
    assert body["total_tokens"] == 15


def test_api_falls_back_when_ai_schema_is_invalid() -> None:
    provider = _StaticProvider(
        json.dumps({"machine": "Pump 9", "severity": "urgent"})
    )
    app = _app(provider, default_provider="json")

    with TestClient(app) as client:
        response = _post(client, "Machine: Pump 7\nFault: Seal leak")

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["extraction_reason"] == "ai_invalid_schema"
    assert body["summary"]["machine"] == "Pump 7"
    # Deterministic signal from the explicit "leak"; the AI's "urgent" is not
    # accepted because it is outside the validated severity contract.
    assert body["summary"]["severity"] == "medium"


def test_api_uses_deterministic_data_when_ai_summary_is_empty() -> None:
    provider = _StaticProvider(
        json.dumps({field: None for field in VALID_SUMMARY})
    )
    app = _app(provider, default_provider="json")

    with TestClient(app) as client:
        response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["extraction_reason"] == "ai_empty_summary"
    assert body["summary"]["fault_description"] == (
        "Bearing seized after abnormal vibration"
    )


def test_api_falls_back_to_deterministic_when_provider_chain_fails() -> None:
    broken = _FailingProvider()
    app = _app(broken, default_provider="broken", reliability_max_attempts=1)

    with TestClient(app) as client:
        response = _post(client, PROSE_REPORT)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["extraction_reason"] == "provider_unavailable"
    assert body["summary"]["machine"] == "Pump 3"
    assert body["summary"]["downtime"] == "45 minutes"
    assert body["selected_provider"] == "broken"
    assert body["provider"] is None
    assert body["total_tokens"] == 0
    assert body["providers_tried"] == ["broken"]
    assert body["fallback_used"] is False
    assert broken.calls == 1


def test_api_reports_chain_metadata_after_unusable_fallback_output() -> None:
    broken = _FailingProvider()
    fallback = FakeProvider(name="fake")
    app = _app(
        broken,
        fallback,
        default_provider="broken",
        reliability_fallback_provider="fake",
        reliability_max_attempts=1,
    )

    with TestClient(app) as client:
        response = _post(client, LABELED_REPORT)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["extraction_reason"] == "ai_invalid_json"
    assert body["provider"] == "fake"
    assert body["providers_tried"] == ["broken", "fake"]
    assert body["fallback_used"] is True
    assert body["fallback_reason"] == "provider_unavailable"
    assert body["summary"]["machine"] == "Conveyor 3"


def test_api_uses_default_fake_provider_without_ai() -> None:
    with TestClient(create_app(_settings())) as client:
        response = _post(client, UNKNOWN_REPORT)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] == "deterministic"
    assert body["provider"] == "fake"
    assert body["summary"] == {
        "machine": None,
        "fault_description": None,
        "temperature": None,
        "temperature_unit": None,
        "downtime": None,
        "action_taken": None,
        "severity": None,
    }
    assert body["missing_fields"] == [
        "machine",
        "fault_description",
        "temperature",
        "downtime",
        "action_taken",
        "severity",
    ]


def test_api_rejects_malformed_requests() -> None:
    with TestClient(create_app(_settings())) as client:
        too_short = _post(client, "short")
        blank = _post(client, " " * 10)
        oversized = _post(client, "x" * 8001)
        extra = _post(client, LABELED_REPORT, unexpected="value")

    assert too_short.status_code == 422
    assert blank.status_code == 422
    assert oversized.status_code == 422
    assert extra.status_code == 422


def test_api_rejects_unknown_provider_without_fallback() -> None:
    with TestClient(create_app(_settings())) as client:
        response = _post(client, LABELED_REPORT, provider="ghost")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "provider_not_found"


def test_api_rejects_unsupported_model_without_fallback() -> None:
    provider = _StaticProvider(json.dumps(VALID_SUMMARY))
    app = _app(provider, default_provider="json")

    with TestClient(app) as client:
        response = _post(client, LABELED_REPORT, model="unknown-model")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_invalid_request"
    assert provider.calls == 1


def test_api_requires_authentication_when_enabled() -> None:
    key = "fault-user-key-1234567890"
    provider = _StaticProvider(json.dumps(VALID_SUMMARY))
    app = _app(
        provider,
        default_provider="json",
        security_require_auth=True,
        security_api_keys=key,
    )

    with TestClient(app) as client:
        anonymous = _post(client)
        authenticated = client.post(
            "/api/v1/fault-reports/summarize",
            json={"report": LABELED_REPORT},
            headers={"Authorization": f"Bearer {key}"},
        )

    assert anonymous.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["extraction"] == "provider"


def test_api_enforces_budget_before_calling_provider() -> None:
    provider = _StaticProvider(json.dumps(VALID_SUMMARY))
    app = _app(
        provider,
        default_provider="json",
        budget_per_request_usd=Decimal("0.000001"),
        budget_daily_usd=Decimal("1"),
        budget_monthly_usd=Decimal("10"),
        budget_provider_pricing={
            "json": PricingRates(
                input_per_million_usd=Decimal("1"),
                output_per_million_usd=Decimal("1"),
            )
        },
    )

    with TestClient(app) as client:
        response = _post(client)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "budget_exceeded"
    assert provider.calls == 0


def test_fault_report_max_tokens_setting_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, fault_report_max_tokens=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, fault_report_max_tokens=8193)


def test_api_logs_summary_without_report_content(caplog) -> None:
    caplog.set_level(logging.INFO)
    provider = _StaticProvider(json.dumps(VALID_SUMMARY))
    app = _app(provider, default_provider="json")
    report = (
        "CONFIDENTIAL-LINE-42: Conveyor 3 bearing seized at 87 C after "
        "abnormal vibration for 2 hours. Replaced the bearing."
    )

    with TestClient(app) as client:
        response = _post(client, report)

    assert response.status_code == 200
    records = [
        record for record in caplog.records if record.name == "app.api.faults"
    ]
    assert records
    summary = records[-1]
    assert summary.event == "fault_report.summary"
    assert summary.extraction == "provider"
    assert summary.provider == "json"
    assert summary.model == "json-model"
    assert summary.total_tokens == 15
    assert summary.missing_field_count == 0
    assert summary.duration_ms >= 0.0
    assert summary.status == "success"

    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert "CONFIDENTIAL-LINE-42" not in logged
    assert "Bearing seized" not in logged
