"""Golden contract baselines for the stable Stage A-I HTTP surface."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from app.core.config import Settings
from app.main import create_app
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from fastapi.testclient import TestClient

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_MANIFEST = PROJECT_ROOT / "config" / "model_versions.json"
BASELINE_DIR = Path(__file__).resolve().parent / "regression" / "baselines"
UPDATE_ENV = "UPDATE_REGRESSION_BASELINES"

FAULT_REPORT = (
    "Machine: Conveyor 3\n"
    "Fault: bearing overheating\n"
    "Temperature: 87 C\n"
    "Downtime: 12 minutes\n"
    "Action taken: Replaced bearing\n"
    "Severity: high"
)
PROVIDER_SUMMARY_JSON = json.dumps(
    {
        "machine": "Press 4",
        "fault_description": "Hydraulic pressure dropped",
        "temperature": 82.0,
        "temperature_unit": "C",
        "downtime": "25 minutes",
        "action_taken": "Replaced seal",
        "severity": "high",
    },
    sort_keys=True,
)


class _JsonProvider(FakeProvider):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=PROVIDER_SUMMARY_JSON,
            usage=TokenUsage(
                prompt_tokens=18,
                completion_tokens=24,
                total_tokens=42,
            ),
            finish_reason="stop",
            latency_ms=0.0,
        )


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "test",
        "log_level": "WARNING",
        "log_format": "console",
        "security_rate_limit_requests": 0,
        "budget_enforcement_enabled": False,
        "database_enabled": False,
        "model_version_manifest": str(PROJECT_MANIFEST),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def regression_client():
    with TestClient(create_app(_settings())) as client:
        yield client


def _snapshot(name: str, status_code: int, body: object) -> None:
    actual = {"status_code": status_code, "body": body}
    serialized = json.dumps(actual, indent=2, sort_keys=True) + "\n"
    path = BASELINE_DIR / f"{name}.json"

    if os.getenv(UPDATE_ENV) == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        return

    assert path.is_file(), (
        f"Missing regression baseline '{path.name}'. Run "
        "scripts\\regression.ps1 -Update to create it."
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"Regression baseline '{path.name}' changed. Review the contract diff; "
        "run scripts\\regression.ps1 -Update only for intended changes."
    )


def _generation_body() -> dict:
    return {
        "messages": [
            {"role": "system", "content": "Answer tersely."},
            {"role": "user", "content": "Pump 7 vibration is high."},
        ],
        "temperature": 0.2,
        "max_tokens": 8,
    }


def test_generation_contract_snapshot(regression_client) -> None:
    response = regression_client.post(
        "/api/v1/generate",
        json=_generation_body(),
        headers={"X-Request-ID": "regression-generation-001"},
    )

    assert response.status_code == 200
    body = response.json()
    body.pop("latency_ms")
    _snapshot("generation", response.status_code, body)


def test_fault_report_deterministic_contract_snapshot(regression_client) -> None:
    response = regression_client.post(
        "/api/v1/fault-reports/summarize",
        json={"report": FAULT_REPORT},
        headers={"X-Request-ID": "regression-fault-deterministic-001"},
    )

    assert response.status_code == 200
    assert response.json()["extraction"] == "deterministic"
    _snapshot(
        "fault_report_deterministic",
        response.status_code,
        response.json(),
    )


def test_fault_report_provider_contract_snapshot() -> None:
    registry = ProviderRegistry()
    registry.register(_JsonProvider(name="fake"))
    app = create_app(_settings(), registry=registry)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/fault-reports/summarize",
            json={"report": FAULT_REPORT},
            headers={"X-Request-ID": "regression-fault-provider-001"},
        )

    assert response.status_code == 200
    assert response.json()["extraction"] == "provider"
    _snapshot("fault_report_provider", response.status_code, response.json())


def test_error_contract_snapshot(regression_client) -> None:
    response = regression_client.post(
        "/api/v1/generate",
        json={
            "messages": [{"role": "user", "content": "Use an unsupported model."}],
            "model": "missing-model",
        },
        headers={"X-Request-ID": "regression-error-001"},
    )

    assert response.status_code == 400
    _snapshot("unsupported_model_error", response.status_code, response.json())


def test_provider_catalog_contract_snapshot(regression_client) -> None:
    response = regression_client.get("/api/v1/providers")

    assert response.status_code == 200
    _snapshot("provider_catalog", response.status_code, response.json())


def test_model_version_catalog_contract_snapshot(regression_client) -> None:
    response = regression_client.get("/api/v1/model-versions")

    assert response.status_code == 200
    _snapshot("model_version_catalog", response.status_code, response.json())


def test_readiness_contract_snapshot(regression_client) -> None:
    response = regression_client.get("/health/ready")

    assert response.status_code == 200
    _snapshot("readiness", response.status_code, response.json())
