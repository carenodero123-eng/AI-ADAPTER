"""Public fault-report request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.faults.models import ExtractionMode, FaultSummary


class FaultReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: str = Field(min_length=10, max_length=8000)
    provider: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
        max_length=32,
    )
    model: str | None = Field(default=None, max_length=100)

    @field_validator("report", "model")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class FaultSummaryResponse(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    summary: FaultSummary
    extraction: ExtractionMode
    extraction_reason: str | None = Field(default=None, max_length=64)
    missing_fields: list[str] = Field(default_factory=list, max_length=6)
    selected_provider: str = Field(min_length=1, max_length=32)
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=100)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    retry_count: int = Field(default=0, ge=0, le=100)
    fallback_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=64)
    providers_tried: list[str] = Field(default_factory=list, max_length=10)
