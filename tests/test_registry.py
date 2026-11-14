"""Provider registry behavior tests."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from app.providers.base import AIProvider
from app.providers.errors import (
    ProviderInvalidResponseError,
    ProviderNotFoundError,
    ProviderTimeoutError,
)
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    GenerationRequest,
    GenerationResult,
    ProviderHealth,
)


class StubProvider(AIProvider):
    def __init__(
        self,
        *,
        name: str = "stub",
        models: Sequence[str] = ("stub-model",),
        default_model: str = "stub-model",
        health_provider: str | None = None,
    ) -> None:
        self._name = name
        self._models = tuple(models)
        self._default_model = default_model
        self._health_provider = health_provider or name
        self.closed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return "Stub Provider"

    @property
    def kind(self) -> str:
        return "stub"

    @property
    def models(self) -> Sequence[str]:
        return self._models

    @property
    def default_model(self) -> str:
        return self._default_model

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        raise ProviderTimeoutError("stub timeout", provider=self.name)

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self._health_provider, status="healthy")

    async def aclose(self) -> None:
        self.closed = True


def test_register_and_lookup_are_sorted_and_case_insensitive() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="zeta"))
    registry.register(FakeProvider(name="alpha"))

    assert registry.names == ("alpha", "zeta")
    assert [provider.name for provider in registry.list_providers()] == ["alpha", "zeta"]
    assert registry.get("  ALPHA ").name == "alpha"
    assert "zeta" in registry


def test_duplicate_and_invalid_names_are_rejected() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider(name="fake"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeProvider(name="fake"))

    with pytest.raises(ValueError, match="provider name"):
        registry.register(FakeProvider(name="Invalid Name"))


def test_invalid_provider_definition_is_rejected() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ValueError, match="at least one model"):
        registry.register(StubProvider(models=()))

    with pytest.raises(ValueError, match="default model"):
        registry.register(
            StubProvider(models=("a",), default_model="missing")
        )


def test_unknown_provider_raises_normalized_error() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ProviderNotFoundError) as error:
        registry.get("ghost")

    assert error.value.code == "provider_not_found"
    assert error.value.provider == "ghost"


@pytest.mark.asyncio
async def test_health_is_forwarded_and_identity_checked() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider(name="good"))
    registry.register(StubProvider(name="liar", health_provider="other"))

    health = await registry.health("good")
    assert health.status == "healthy"

    with pytest.raises(ProviderInvalidResponseError):
        await registry.health("liar")


@pytest.mark.asyncio
async def test_close_all_closes_every_provider() -> None:
    registry = ProviderRegistry()
    first = StubProvider(name="first")
    second = StubProvider(name="second")
    registry.register(first)
    registry.register(second)

    await registry.aclose()

    assert first.closed is True
    assert second.closed is True
