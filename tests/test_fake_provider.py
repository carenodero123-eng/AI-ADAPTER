"""Deterministic local fake-provider tests."""

from __future__ import annotations

import pytest
from app.providers.errors import ProviderInvalidRequestError
from app.providers.fake import FakeProvider
from app.providers.schemas import ChatMessage, GenerationRequest


def _request(
    *,
    model: str = "fake-small",
    max_tokens: int | None = None,
    temperature: float = 0.0,
    include_user: bool = True,
) -> GenerationRequest:
    messages = [ChatMessage(role="system", content="Be terse")]
    if include_user:
        messages.append(ChatMessage(role="user", content="Compressor overheated"))
    return GenerationRequest(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )


@pytest.mark.asyncio
async def test_generate_is_deterministic_and_normalized() -> None:
    provider = FakeProvider()

    first = await provider.generate(_request())
    second = await provider.generate(_request())

    assert first.content == "[fake:fake-small] Compressor overheated"
    assert second.content == first.content
    assert first.provider == "fake"
    assert first.model == "fake-small"
    assert first.finish_reason == "stop"
    assert first.usage.prompt_tokens == 4
    assert first.usage.completion_tokens == 3
    assert first.usage.total_tokens == 7
    assert first.latency_ms >= 0


@pytest.mark.asyncio
async def test_temperature_does_not_change_fake_output() -> None:
    provider = FakeProvider()

    cold = await provider.generate(_request(temperature=0.0))
    hot = await provider.generate(_request(temperature=2.0))

    assert hot.content == cold.content


@pytest.mark.asyncio
async def test_max_tokens_truncates_deterministically() -> None:
    provider = FakeProvider()

    result = await provider.generate(_request(max_tokens=2))

    assert result.content == "[fake:fake-small] Compressor"
    assert result.finish_reason == "length"
    assert result.usage.completion_tokens == 2
    assert result.usage.total_tokens == 6


@pytest.mark.asyncio
async def test_model_switch_changes_model_and_output() -> None:
    provider = FakeProvider()

    result = await provider.generate(_request(model="fake-large"))

    assert result.model == "fake-large"
    assert result.content.startswith("[fake:fake-large] ")


@pytest.mark.asyncio
async def test_unknown_model_is_rejected() -> None:
    provider = FakeProvider()

    with pytest.raises(ProviderInvalidRequestError) as error:
        await provider.generate(_request(model="unknown-model"))

    assert error.value.code == "provider_invalid_request"
    assert error.value.provider == "fake"
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_user_message_is_required() -> None:
    provider = FakeProvider()

    with pytest.raises(ProviderInvalidRequestError):
        await provider.generate(_request(include_user=False))


@pytest.mark.asyncio
async def test_healthcheck_reports_healthy() -> None:
    provider = FakeProvider()

    health = await provider.healthcheck()

    assert health.provider == "fake"
    assert health.status == "healthy"
    assert health.latency_ms is not None


def test_custom_models_and_invalid_default() -> None:
    provider = FakeProvider(models=["alpha"], default_model="alpha")
    assert provider.models == ("alpha",)
    assert provider.default_model == "alpha"

    with pytest.raises(ValueError):
        FakeProvider(models=["alpha"], default_model="beta")
