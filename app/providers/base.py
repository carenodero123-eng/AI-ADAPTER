"""The single provider interface implemented by every adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.providers.schemas import (
    GenerationRequest,
    GenerationResult,
    ProviderHealth,
    ProviderInfo,
)


class AIProvider(ABC):
    """Provider-independent async interface.

    Vendor SDKs, HTTP shapes, and error payloads stay inside concrete
    adapters. Callers only see normalized requests, results, health, and
    errors.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable registry key, for example ``fake`` or ``openai``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider label."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Adapter family, for example ``fake`` or ``openai``."""

    @property
    @abstractmethod
    def models(self) -> Sequence[str]:
        """Models explicitly supported by this provider configuration."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Model used when a caller does not specify one."""

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            models=list(self.models),
            default_model=self.default_model,
        )

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Execute a generation request and return a normalized result."""

    @abstractmethod
    async def healthcheck(self) -> ProviderHealth:
        """Report current provider availability using a bounded check."""

    async def aclose(self) -> None:  # noqa: B027 - optional cleanup hook
        """Release provider resources. Adapters without resources may skip."""
