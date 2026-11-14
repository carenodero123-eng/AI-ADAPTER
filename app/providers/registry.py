"""Registry of configured providers with normalized lookup and health."""

from __future__ import annotations

import logging
import re

from app.providers.base import AIProvider
from app.providers.errors import (
    ProviderInvalidResponseError,
    ProviderNotFoundError,
)
from app.providers.schemas import ProviderHealth

logger = logging.getLogger("app.providers.registry")

_PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class ProviderRegistry:
    """In-process provider catalog populated during application startup."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        name = provider.name.strip()
        if not _PROVIDER_NAME.fullmatch(name):
            raise ValueError(
                "provider name must match ^[a-z][a-z0-9_-]{0,31}$"
            )
        if name in self._providers:
            raise ValueError(f"provider '{name}' is already registered")
        if not provider.models:
            raise ValueError(f"provider '{name}' must declare at least one model")
        if provider.default_model not in provider.models:
            raise ValueError(
                f"default model '{provider.default_model}' is not listed by provider '{name}'"
            )
        self._providers[name] = provider

    def get(self, name: str) -> AIProvider:
        key = name.strip().lower()
        provider = self._providers.get(key)
        if provider is None:
            raise ProviderNotFoundError(
                f"Provider '{key}' is not registered.",
                provider=key,
            )
        return provider

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip().lower() in self._providers

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def list_providers(self) -> list[AIProvider]:
        return [self._providers[name] for name in sorted(self._providers)]

    async def health(self, name: str) -> ProviderHealth:
        provider = self.get(name)
        health = await provider.healthcheck()
        if health.provider != provider.name:
            raise ProviderInvalidResponseError(
                "Provider health response did not match the provider identity.",
                provider=provider.name,
            )
        return health

    async def aclose(self) -> None:
        for provider in reversed(self.list_providers()):
            try:
                await provider.aclose()
            except Exception:
                logger.exception(
                    "provider.close_failed",
                    extra={"event": "provider.close_failed", "provider": provider.name},
                )
