"""Normalized provider request, result, and health schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MessageRole = Literal["system", "user", "assistant"]
FinishReason = Literal["stop", "length", "content_filter"]
ProviderStatus = Literal["healthy", "degraded", "unavailable"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message content must not be blank")
        return value


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=100)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)

    @field_validator("model")
    @classmethod
    def _strip_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model must not be blank")
        return value


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _total_matches_parts(self) -> TokenUsage:
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")
        return self


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=100)
    content: str
    usage: TokenUsage
    finish_reason: FinishReason = "stop"
    latency_ms: float = Field(ge=0.0)


class ProviderInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=32)
    models: list[str] = Field(min_length=1)
    default_model: str = Field(min_length=1, max_length=100)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=32)
    status: ProviderStatus
    latency_ms: float | None = Field(default=None, ge=0.0)
    detail: str | None = Field(default=None, max_length=500)
