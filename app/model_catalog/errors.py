"""Errors raised while building or exposing the model version catalog."""

from __future__ import annotations

from app.core.errors import ApplicationError


class ModelCatalogConfigurationError(ValueError):
    """The configured model version manifest is missing or inconsistent."""


class ModelCatalogUnavailableError(ApplicationError):
    code = "model_catalog_unavailable"
    status_code = 503
    retryable = False

    def __init__(self) -> None:
        super().__init__(
            "The model version catalog is not configured for this deployment."
        )
