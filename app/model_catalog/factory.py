"""Build the model version catalog for the configured provider registry."""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.model_catalog.errors import ModelCatalogConfigurationError
from app.model_catalog.manifest import load_model_catalog
from app.model_catalog.versions import ModelCatalog
from app.providers.registry import ProviderRegistry

logger = logging.getLogger("app.model_catalog.factory")


def validate_model_catalog(
    catalog: ModelCatalog,
    registry: ProviderRegistry,
    *,
    default_provider: str,
) -> None:
    """Fail closed when configured models lack safe version metadata."""

    if default_provider not in registry:
        raise ModelCatalogConfigurationError(
            f"Default provider '{default_provider}' is not registered."
        )

    for provider in registry.list_providers():
        for model in provider.models:
            entry = catalog.get(provider.name, model)
            if entry is None:
                raise ModelCatalogConfigurationError(
                    f"Configured model '{model}' for provider "
                    f"'{provider.name}' has no entry in the model version manifest."
                )
            if entry.status == "retired":
                raise ModelCatalogConfigurationError(
                    f"Configured model '{provider.name}/{model}' is retired; "
                    "remove it from provider configuration or use another model."
                )
            if entry.status == "deprecated":
                logger.warning(
                    "model.version.deprecated",
                    extra={
                        "event": "model.version.deprecated",
                        "provider": provider.name,
                        "model": model,
                        "version": entry.version,
                    },
                )

    default = registry.get(default_provider)
    default_entry = catalog.get(default_provider, default.default_model)
    if default_entry is None:
        raise ModelCatalogConfigurationError(
            f"Default model '{default_provider}/{default.default_model}' "
            "has no entry in the model version manifest."
        )
    if default_entry.status != "active":
        raise ModelCatalogConfigurationError(
            f"Default model '{default_provider}/{default.default_model}' "
            f"has status '{default_entry.status}'; the default model must be active."
        )


def build_model_catalog(
    settings: Settings,
    registry: ProviderRegistry,
) -> ModelCatalog | None:
    """Return ``None`` when model version management is not enabled."""

    manifest = settings.model_version_manifest.strip()
    if not manifest:
        return None

    catalog = load_model_catalog(manifest)
    validate_model_catalog(
        catalog,
        registry,
        default_provider=settings.default_provider,
    )
    return catalog
