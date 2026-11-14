"""Public generation request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.schemas import ChatMessage, GenerationResult


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
        max_length=32,
    )
    model: str | None = Field(default=None, max_length=100)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)

    @field_validator("model")
    @classmethod
    def _strip_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("model must not be blank")
        return value


class GenerateResponse(GenerationResult):
    request_id: str = Field(min_length=1, max_length=64)
    requested_provider: str = Field(min_length=1, max_length=32)
    retry_count: int = Field(default=0, ge=0, le=100)
    fallback_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=64)
    providers_tried: list[str] = Field(default_factory=list, max_length=10)
    cost_usd: float = Field(default=0.0, ge=0.0)
