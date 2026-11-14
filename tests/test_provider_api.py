"""Provider API, switching, validation, and safe error tests."""

from __future__ import annotations

import logging

import pytest
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import ProviderServerError
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from fastapi.testclient import TestClient


def _body(**overrides):
    body = {
        "messages": [
            {"role": "system", "content": "Be terse"},
            {"role": "user", "content": "Compressor overheated"},
        ]
    }
    body.update(overrides)
    return body


def test_list_providers_exposes_default_and_models(client) -> None:
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    providers = response.json()
    assert providers == [
        {
            "name": "fake",
            "display_name": "Local Fake Provider",
            "kind": "fake",
            "models": ["fake-small", "fake-large"],
            "default_model": "fake-small",
            "is_default": True,
        }
    ]


def test_provider_detail_health_and_not_found(client) -> None:
    detail = client.get("/api/v1/providers/fake")
    health = client.get("/api/v1/providers/fake/health")
    missing = client.get(
        "/api/v1/providers/ghost",
        headers={"X-Request-ID": "missing-provider-001"},
    )

    assert detail.status_code == 200
    assert detail.json()["name"] == "fake"
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "provider_not_found",
        "message": "Provider 'ghost' is not registered.",
        "provider": "ghost",
        "retryable": False,
    }
    assert missing.json()["request_id"] == "missing-provider-001"
    assert missing.headers["X-Request-ID"] == "missing-provider-001"


def test_generate_uses_default_provider_and_model(client) -> None:
    response = client.post("/api/v1/generate", json=_body())

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "fake"
    assert result["model"] == "fake-small"
    assert result["content"] == "[fake:fake-small] Compressor overheated"
    assert result["finish_reason"] == "stop"
    assert result["usage"] == {
        "prompt_tokens": 4,
        "completion_tokens": 3,
        "total_tokens": 7,
    }
    assert result["request_id"] == response.headers["X-Request-ID"]


def test_generate_selects_model_and_respects_max_tokens(client) -> None:
    response = client.post(
        "/api/v1/generate",
        json=_body(model="fake-large", max_tokens=2),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "fake-large"
    assert result["content"] == "[fake:fake-large] Compressor"
    assert result["finish_reason"] == "length"


def test_provider_switching_between_registered_adapters() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))
    registry.register(
        FakeProvider(
            name="fake-alt",
            display_name="Alternate Fake",
            models=["alt-model"],
            default_model="alt-model",
        )
    )
    app = create_app(settings, registry=registry)

    with TestClient(app) as client:
        providers = client.get("/api/v1/providers").json()
        alternate = client.post(
            "/api/v1/generate",
            json=_body(provider="fake-alt"),
        )
        default = client.post("/api/v1/generate", json=_body())

    assert [item["name"] for item in providers] == ["fake", "fake-alt"]
    assert [item["is_default"] for item in providers] == [True, False]
    assert alternate.status_code == 200
    assert alternate.json()["provider"] == "fake-alt"
    assert alternate.json()["model"] == "alt-model"
    assert default.json()["provider"] == "fake"


def test_unknown_provider_returns_404(client) -> None:
    response = client.post("/api/v1/generate", json=_body(provider="ghost"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "provider_not_found"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unsupported_model_returns_400(client) -> None:
    response = client.post("/api/v1/generate", json=_body(model="unknown-model"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_invalid_request"
    assert response.json()["error"]["retryable"] is False
    assert "unknown-model" in response.json()["error"]["message"]


def test_malformed_requests_return_422(client) -> None:
    assert client.post("/api/v1/generate", json={"messages": []}).status_code == 422
    assert (
        client.post(
            "/api/v1/generate",
            json=_body(messages=[{"role": "user", "content": "   "}]),
        ).status_code
        == 422
    )
    assert client.post("/api/v1/generate", json=_body(temperature=3.0)).status_code == 422
    assert client.post("/api/v1/generate", json=_body(provider="FAKE")).status_code == 422
    assert client.post("/api/v1/generate", json=_body(extra="ignored")).status_code == 422


def test_provider_error_response_is_sanitized(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.providers")

    class LeakingProvider(FakeProvider):
        async def generate(self, request):
            raise ProviderServerError(
                "Upstream rejected Bearer super-secret-token and sk-abcdefgh12345",
                provider=self.name,
            )

    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
        reliability_max_attempts=1,
        reliability_secondary_provider="",
        reliability_fallback_provider="",
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))
    registry.register(LeakingProvider(name="leaky"))
    app = create_app(settings, registry=registry)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/generate",
            json=_body(provider="leaky"),
            headers={"X-Request-ID": "sanitize-error-001"},
        )

    body = response.json()
    assert response.status_code == 502
    assert body["error"]["code"] == "provider_server_error"
    assert body["error"]["retryable"] is True
    assert body["request_id"] == "sanitize-error-001"
    assert "super-secret-token" not in body["error"]["message"]
    assert "sk-abcdefgh12345" not in body["error"]["message"]
    assert "[REDACTED]" in body["error"]["message"]

    logged = " ".join(
        str(getattr(record, "error_message", "")) for record in caplog.records
    )
    assert logged
    assert "super-secret-token" not in logged
    assert "sk-abcdefgh12345" not in logged


def test_generate_does_not_log_prompt_content(client, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "SENSITIVE-PROMPT-MARKER"

    response = client.post(
        "/api/v1/generate",
        json=_body(
            messages=[{"role": "user", "content": marker}],
        ),
    )

    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert response.status_code == 200
    assert marker in response.json()["content"]
    assert marker not in logged


def test_injected_registry_must_contain_default_provider() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        default_provider="ghost",
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))

    with pytest.raises(ValueError, match="DEFAULT_PROVIDER"):
        create_app(settings, registry=registry)
