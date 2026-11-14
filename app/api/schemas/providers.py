"""Provider catalog and health response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.providers.schemas import ProviderHealth, ProviderInfo


class ProviderSummary(ProviderInfo):
    is_default: bool


class CircuitStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["closed", "open", "half_open"]
    failure_count: int = Field(ge=0)
    recovery_remaining_seconds: float | None = Field(default=None, ge=0.0)


class ProviderHealthReport(ProviderHealth):
    circuit: CircuitStatus | None = None
