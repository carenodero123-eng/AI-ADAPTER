"""OpenAI chat-completions adapter built on HTTPX."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import httpx

from app.providers.base import AIProvider
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.schemas import (
    FinishReason,
    GenerationRequest,
    GenerationResult,
    ProviderHealth,
    ProviderStatus,
    TokenUsage,
)

_FINISH_REASONS: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
}

_AUTH_STATUSES = {401, 403}
_INVALID_REQUEST_STATUSES = {400, 404, 422}


class OpenAIProvider(AIProvider):
    """Async adapter for the OpenAI ``/chat/completions`` endpoint.

    Vendor payloads and failures are translated into the normalized provider
    schemas and error taxonomy. The API key is held as a string only to build
    the Authorization header and is never included in results, health data,
    or error messages.
    """

    def __init__(
        self,
        *,
        api_key: str,
        models: Sequence[str],
        default_model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
        name: str = "openai",
        display_name: str = "OpenAI",
    ) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("api_key must not be blank")

        normalized = tuple(
            dict.fromkeys(model.strip() for model in models if model.strip())
        )
        if not normalized:
            raise ValueError("models must contain at least one model")

        resolved_default = default_model.strip()
        if resolved_default not in normalized:
            raise ValueError(
                f"default model '{resolved_default}' is not in the configured model list"
            )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        self._name = name
        self._display_name = display_name
        self._models = normalized
        self._default_model = resolved_default
        self._base_url = base_url.strip().rstrip("/")
        self._timeout = timeout_seconds
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client = http_client or httpx.AsyncClient(trust_env=False)
        self._owns_client = http_client is None

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def kind(self) -> str:
        return "openai"

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

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name} request timed out after {self._timeout:g}s.",
                provider=self.name,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"{self.display_name} endpoint is unreachable.",
                provider=self.name,
            ) from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 3)

        if not response.is_success:
            raise self._error_for_status(response.status_code)

        data = self._json_object(response)
        content, finish_reason = self._extract_choice(data)
        usage = self._extract_usage(data)

        return GenerationResult(
            provider=self.name,
            model=request.model,
            content=content,
            usage=usage,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    async def healthcheck(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            response = await self._client.get(
                f"{self._base_url}/models",
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return self._health("unavailable", started, "Request timed out.")
        except httpx.HTTPError:
            return self._health("unavailable", started, "Endpoint is unreachable.")

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if response.status_code in _AUTH_STATUSES:
            return self._health(
                "unavailable", started, "Authentication failed.", latency_ms
            )
        if response.status_code >= 500:
            return self._health(
                "degraded", started, "Upstream service error.", latency_ms
            )
        if not response.is_success:
            return self._health(
                "unavailable", started, "Models endpoint rejected the request.", latency_ms
            )

        try:
            data = response.json()
        except ValueError:
            return self._health(
                "degraded", started, "Models endpoint returned invalid JSON.", latency_ms
            )
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return self._health(
                "degraded", started, "Models endpoint returned an unexpected payload.", latency_ms
            )
        return self._health("healthy", started, None, latency_ms)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _error_for_status(self, status_code: int) -> ProviderError:
        if status_code in _AUTH_STATUSES:
            return ProviderAuthenticationError(
                f"{self.display_name} authentication failed (HTTP {status_code}).",
                provider=self.name,
            )
        if status_code == 429:
            return ProviderRateLimitError(
                f"{self.display_name} rate limit exceeded (HTTP 429).",
                provider=self.name,
            )
        if status_code >= 500:
            return ProviderServerError(
                f"{self.display_name} service error (HTTP {status_code}).",
                provider=self.name,
            )
        if status_code in _INVALID_REQUEST_STATUSES:
            return ProviderInvalidRequestError(
                f"{self.display_name} rejected the request (HTTP {status_code}).",
                provider=self.name,
            )
        return ProviderUnavailableError(
            f"{self.display_name} returned an unexpected status (HTTP {status_code}).",
            provider=self.name,
        )

    def _json_object(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned a non-JSON response.",
                provider=self.name,
            ) from exc
        if not isinstance(data, dict):
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned an unexpected response shape.",
                provider=self.name,
            )
        return data

    def _extract_choice(self, data: dict[str, Any]) -> tuple[str, FinishReason]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned no choices.",
                provider=self.name,
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned an invalid choice.",
                provider=self.name,
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned an invalid message.",
                provider=self.name,
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned no text content.",
                provider=self.name,
            )
        raw_reason = choice.get("finish_reason")
        finish_reason = (
            _FINISH_REASONS.get(raw_reason, "stop")
            if isinstance(raw_reason, str)
            else "stop"
        )
        return content, finish_reason

    def _extract_usage(self, data: dict[str, Any]) -> TokenUsage:
        raw_usage = data.get("usage")
        if raw_usage is None:
            return TokenUsage(
                prompt_tokens=0, completion_tokens=0, total_tokens=0
            )
        if not isinstance(raw_usage, dict):
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned invalid usage data.",
                provider=self.name,
            )
        prompt_tokens = self._token_count(raw_usage, "prompt_tokens")
        completion_tokens = self._token_count(raw_usage, "completion_tokens")
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def _token_count(self, usage: dict[str, Any], field: str) -> int:
        value = usage.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProviderInvalidResponseError(
                f"{self.display_name} returned invalid usage data.",
                provider=self.name,
            )
        return value

    def _health(
        self,
        status: ProviderStatus,
        started: float,
        detail: str | None,
        latency_ms: float | None = None,
    ) -> ProviderHealth:
        if latency_ms is None:
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return ProviderHealth(
            provider=self.name,
            status=status,
            latency_ms=latency_ms,
            detail=detail,
        )
