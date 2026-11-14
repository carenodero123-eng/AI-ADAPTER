"""Build the provider registry from application settings."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider
from app.providers.registry import ProviderRegistry


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(
            models=settings.fake_model_list,
            default_model=settings.fake_provider_default_model,
        )
    )

    api_key = settings.openai_api_key
    if api_key is not None:
        registry.register(
            OpenAIProvider(
                api_key=api_key.get_secret_value(),
                base_url=settings.openai_base_url,
                models=settings.openai_model_list,
                default_model=settings.openai_default_model,
                timeout_seconds=settings.openai_timeout_seconds,
            )
        )
    elif settings.default_provider == "openai":
        raise ValueError(
            "DEFAULT_PROVIDER 'openai' requires OPENAI_API_KEY to be configured"
        )

    if settings.default_provider not in registry:
        raise ValueError(
            f"DEFAULT_PROVIDER '{settings.default_provider}' is not registered; "
            f"available providers: {', '.join(registry.names)}"
        )
    return registry
