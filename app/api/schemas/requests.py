"""Administrative request-history response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=64)
    kind: Literal["generation", "fault_report"]
    occurred_at: datetime
    auth_role: str | None = Field(default=None, max_length=16)
    selected_provider: str | None = Field(default=None, max_length=32)
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=100)
    duration_ms: float = Field(ge=0.0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    retry_count: int = Field(ge=0)
    fallback_used: bool
    fallback_reason: str | None = Field(default=None, max_length=128)
    providers_tried: list[str] = Field(default_factory=list)
    status: Literal["success", "degraded", "error"]
    error_code: str | None = Field(default=None, max_length=64)
    http_status: int = Field(ge=100, le=599)
    extraction: str | None = Field(default=None, max_length=16)
    extraction_reason: str | None = Field(default=None, max_length=64)
    missing_field_count: int | None = Field(default=None, ge=0)


class RequestLogPage(BaseModel):
    items: list[RequestLogItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
