"""Deterministic in-process provider used for development and tests."""

from __future__ import annotations

import time
from collections.abc import Sequence

from app.providers.base import AIProvider
from app.providers.errors import ProviderInvalidRequestError
from app.providers.schemas import (
    FinishReason,
    GenerationRequest,
    GenerationResult,
    ProviderHealth,
    TokenUsage,
)


def _estimate_tokens(text: str) -> int:
    words = text.split()
    return max(1, len(words)) if words else 0


class FakeProvider(AIProvider):
    """Offline provider with stable, inspectable output.

    Output is an echo of the last user message prefixed with the provider and
    model. Temperature is accepted for interface parity but never changes the
    result. Token counts are deterministic word-based estimates, not a real
    tokenizer.
    """

    def __init__(
        self,
        *,
        name: str = "fake",
        display_name: str = "Local Fake Provider",
        models: Sequence[str] | None = None,
        default_model: str | None = None,
    ) -> None:
        normalized = tuple(
            dict.fromkeys(model.strip() for model in (models or ()) if model.strip())
        )
        if not normalized:
            normalized = ("fake-small", "fake-large")

        resolved_default = default_model or normalized[0]
        if resolved_default not in normalized:
            raise ValueError(
                f"default model '{resolved_default}' is not in the configured model list"
            )

        self._name = name
        self._display_name = display_name
        self._models = normalized
        self._default_model = resolved_default

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def kind(self) -> str:
        return "fake"

    @property
    def models(self) -> Sequence[str]:
        return self._models

    @property
    def default_model(self) -> str:
        return self._default_model

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        if request.model not in self._models:
            raise ProviderInvalidRequestError(
                f"Model '{request.model}' is not supported by provider '{self.name}'.",
                provider=self.name,
            )

        user_messages = [message for message in request.messages if message.role == "user"]
        if not user_messages:
            raise ProviderInvalidRequestError(
                "At least one user message is required.",
                provider=self.name,
            )

        started = time.perf_counter()
        content = f"[{self.name}:{request.model}] {user_messages[-1].content}"
        finish_reason: FinishReason = "stop"

        if request.max_tokens is not None:
            words = content.split()
            if len(words) > request.max_tokens:
                content = " ".join(words[: request.max_tokens])
                finish_reason = "length"

        prompt_tokens = sum(_estimate_tokens(message.content) for message in request.messages)
        completion_tokens = _estimate_tokens(content)
        latency_ms = round((time.perf_counter() - started) * 1000, 3)

        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=content,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    async def healthcheck(self) -> ProviderHealth:
        started = time.perf_counter()
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return ProviderHealth(
            provider=self.name,
            status="healthy",
            latency_ms=latency_ms,
        )
