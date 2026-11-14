"""OpenAI adapter wire-format, error-mapping, and integration tests."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.factory import build_provider_registry
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import ChatMessage, GenerationRequest
from fastapi.testclient import TestClient

TEST_KEY = "sk-test-secret-12345678"
MODELS = ["gpt-4o-mini", "gpt-4o"]


def _request(
    *,
    model: str = "gpt-4o-mini",
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> GenerationRequest:
    return GenerationRequest(
        model=model,
        messages=[
            ChatMessage(role="system", content="Be terse"),
            ChatMessage(role="user", content="Compressor overheated"),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _success_payload(**overrides):
    payload = {
        "id": "chatcmpl-test",
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Check the coolant."},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "total_tokens": 16,
        },
    }
    payload.update(overrides)
    return payload


def _provider(
    *,
    client: httpx.AsyncClient | None = None,
    api_key: str = TEST_KEY,
) -> OpenAIProvider:
    return OpenAIProvider(
        api_key=api_key,
        models=MODELS,
        default_model="gpt-4o-mini",
        base_url="https://api.openai.test/v1/",
        timeout_seconds=5.0,
        http_client=client,
    )


@pytest.mark.asyncio
async def test_generate_sends_normalized_payload_and_returns_result() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_success_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(client=client)
        result = await provider.generate(_request(max_tokens=128))

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.openai.test/v1/chat/completions"
    assert captured["authorization"] == f"Bearer {TEST_KEY}"
    assert captured["body"] == {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Be terse"},
            {"role": "user", "content": "Compressor overheated"},
        ],
        "temperature": 0.2,
        "max_tokens": 128,
    }
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert result.content == "Check the coolant."
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 4
    assert result.usage.total_tokens == 16
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_omits_max_tokens_and_maps_length_finish_reason() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        payload = _success_payload()
        payload["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(client=client).generate(_request())

    assert "max_tokens" not in captured["body"]
    assert result.finish_reason == "length"


@pytest.mark.asyncio
async def test_total_tokens_are_derived_from_parts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_payload()
        payload["usage"]["total_tokens"] = 999
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(client=client).generate(_request())

    assert result.usage.total_tokens == 16


@pytest.mark.asyncio
async def test_missing_usage_is_normalized_to_zeroes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_payload()
        payload.pop("usage")
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(client=client).generate(_request())

    assert result.usage.prompt_tokens == 0
    assert result.usage.completion_tokens == 0
    assert result.usage.total_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type", "retryable"),
    [
        (401, ProviderAuthenticationError, False),
        (403, ProviderAuthenticationError, False),
        (400, ProviderInvalidRequestError, False),
        (404, ProviderInvalidRequestError, False),
        (422, ProviderInvalidRequestError, False),
        (429, ProviderRateLimitError, True),
        (500, ProviderServerError, True),
        (503, ProviderServerError, True),
        (302, ProviderUnavailableError, True),
        (418, ProviderUnavailableError, True),
    ],
)
async def test_http_statuses_map_to_normalized_errors(
    status: int, error_type: type[Exception], retryable: bool
) -> None:
    leaked_marker = f"upstream-body-{status}"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"message": f"{leaked_marker} {TEST_KEY}"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(client=client)
        with pytest.raises(error_type) as error:
            await provider.generate(_request())

    assert error.value.provider == "openai"
    assert error.value.retryable is retryable
    assert TEST_KEY not in str(error.value)
    assert leaked_marker not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_maps_to_retryable_timeout_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderTimeoutError) as error:
            await _provider(client=client).generate(_request())

    assert error.value.retryable is True
    assert TEST_KEY not in str(error.value)


@pytest.mark.asyncio
async def test_transport_failure_maps_to_unavailable_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderUnavailableError) as error:
            await _provider(client=client).generate(_request())

    assert error.value.code == "provider_unavailable"
    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_non_json_response_is_rejected() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>upstream error</html>",
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderInvalidResponseError):
            await _provider(client=client).generate(_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": "not-a-list"},
    ],
)
async def test_malformed_success_payloads_are_rejected(payload: object) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderInvalidResponseError):
            await _provider(client=client).generate(_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1, "completion_tokens": 2},
        {"prompt_tokens": "12", "completion_tokens": 2},
        {"prompt_tokens": True, "completion_tokens": 2},
        "not-a-dict",
    ],
)
async def test_malformed_usage_is_rejected(usage: object) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload(usage=usage))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderInvalidResponseError):
            await _provider(client=client).generate(_request())


@pytest.mark.asyncio
async def test_unknown_model_is_rejected_before_network_call() -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_success_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderInvalidRequestError):
            await _provider(client=client).generate(
                _request(model="gpt-unknown")
            )

    assert called is False


@pytest.mark.asyncio
async def test_healthcheck_uses_models_endpoint_and_reports_healthy() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        health = await _provider(client=client).healthcheck()

    assert captured["url"] == "https://api.openai.test/v1/models"
    assert captured["authorization"] == f"Bearer {TEST_KEY}"
    assert health.provider == "openai"
    assert health.status == "healthy"
    assert health.latency_ms is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "content", "expected_status", "detail"),
    [
        (401, b"{}", "unavailable", "Authentication failed."),
        (500, b"{}", "degraded", "Upstream service error."),
        (400, b"{}", "unavailable", "Models endpoint rejected the request."),
        (302, b"{}", "unavailable", "Models endpoint rejected the request."),
        (200, b"not-json", "degraded", "Models endpoint returned invalid JSON."),
        (200, b'{"data": "wrong"}', "degraded", "Models endpoint returned an unexpected payload."),
    ],
)
async def test_healthcheck_reports_degradation_without_leaking_details(
    status: int, content: bytes, expected_status: str, detail: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        health = await _provider(client=client).healthcheck()

    assert health.status == expected_status
    assert health.detail == detail
    assert TEST_KEY not in (health.detail or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout("timeout"), httpx.ConnectError("refused")]
)
async def test_healthcheck_reports_unavailable_on_network_failure(failure) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        health = await _provider(client=client).healthcheck()

    assert health.status == "unavailable"
    assert TEST_KEY not in (health.detail or "")


@pytest.mark.asyncio
async def test_close_releases_only_owned_client() -> None:
    provider = _provider()
    owned = provider._client  # noqa: SLF001 - lifecycle assertion
    assert owned.is_closed is False

    await provider.aclose()

    assert owned.is_closed is True

    async with httpx.AsyncClient(trust_env=False) as external:
        external_provider = _provider(client=external)
        await external_provider.aclose()
        assert external.is_closed is False


def test_factory_registers_openai_only_when_key_is_configured() -> None:
    without_key = build_provider_registry(Settings(_env_file=None))
    assert without_key.names == ("fake",)

    settings = Settings(
        _env_file=None,
        openai_api_key=TEST_KEY,
        openai_models="gpt-4o-mini,gpt-4o",
        openai_default_model="gpt-4o",
    )
    registry = build_provider_registry(settings)
    try:
        assert registry.names == ("fake", "openai")
        info = registry.get("openai").info()
        assert info.kind == "openai"
        assert info.models == ["gpt-4o-mini", "gpt-4o"]
        assert info.default_model == "gpt-4o"
    finally:
        asyncio.run(registry.aclose())


def test_factory_rejects_openai_default_without_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_provider_registry(
            Settings(_env_file=None, default_provider="openai")
        )


def test_api_routes_generation_to_openai_and_hides_secret(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=_success_payload())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
        default_provider="openai",
        openai_api_key=TEST_KEY,
        openai_models="gpt-4o-mini,gpt-4o",
        openai_default_model="gpt-4o-mini",
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    registry.register(_provider(client=http_client))
    app = create_app(settings, registry=registry)

    try:
        with TestClient(app) as client:
            providers = client.get("/api/v1/providers").json()
            response = client.post(
                "/api/v1/generate",
                json={
                    "messages": [
                        {"role": "user", "content": "Compressor overheated"}
                    ]
                },
                headers={"X-Request-ID": "openai-route-001"},
            )
    finally:
        asyncio.run(http_client.aclose())

    assert [item["name"] for item in providers] == ["fake", "openai"]
    assert [item["is_default"] for item in providers] == [False, True]
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o-mini"
    assert body["content"] == "Check the coolant."
    assert body["request_id"] == "openai-route-001"
    assert captured["authorization"] == f"Bearer {TEST_KEY}"

    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert TEST_KEY not in logged
    assert "Compressor overheated" not in logged


def test_api_maps_openai_authentication_failure_without_leaking_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": f"Incorrect API key {TEST_KEY}"}},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        log_format="console",
        default_provider="openai",
        openai_api_key=TEST_KEY,
        reliability_secondary_provider="",
        reliability_fallback_provider="",
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    registry.register(_provider(client=http_client))
    app = create_app(settings, registry=registry)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/generate",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    finally:
        asyncio.run(http_client.aclose())

    body = response.json()
    assert response.status_code == 502
    assert body["error"]["code"] == "provider_authentication_failed"
    assert body["error"]["retryable"] is False
    assert TEST_KEY not in body["error"]["message"]
