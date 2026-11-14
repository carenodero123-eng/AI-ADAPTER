"""Validated response models for health and system endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    uptime_seconds: float = Field(ge=0.0)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class SystemInfoResponse(BaseModel):
    service: str
    version: str
    environment: str
    api_prefix: str
    docs_url: str | None
    uptime_seconds: float = Field(ge=0.0)
