"""Validated payloads consumed by the dashboard.

These models are deliberately owned by the dashboard layer: the UI depends on
the published HTTP contract, not on application internals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    uptime_seconds: float = Field(ge=0.0)


class ReadinessStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class LatencySummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    average_ms: float = Field(ge=0.0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    min_ms: float | None = Field(default=None, ge=0.0)
    max_ms: float | None = Field(default=None, ge=0.0)
    sample_size: int = Field(ge=0)
    sample_truncated: bool


class PerformanceSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requests: int = Field(ge=0)
    accepted: int = Field(ge=0)
    successful: int = Field(ge=0)
    degraded: int = Field(ge=0)
    errors: int = Field(ge=0)
    accepted_rate: float = Field(ge=0.0, le=1.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    degraded_rate: float = Field(ge=0.0, le=1.0)
    error_rate: float = Field(ge=0.0, le=1.0)
    provider_requests: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    provider_failure_rate: float = Field(ge=0.0, le=1.0)
    fallback_requests: int = Field(ge=0)
    fallback_rate: float = Field(ge=0.0, le=1.0)
    retry_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    cost_per_request_usd: float = Field(ge=0.0)
    cost_per_accepted_result_usd: float = Field(ge=0.0)
    latency: LatencySummary


class KindPerformanceSummary(PerformanceSummary):
    kind: Literal["generation", "fault_report"]


class ProviderPerformanceSummary(PerformanceSummary):
    provider: str


class MonitoringReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window: Literal["15m", "1h", "6h", "24h", "7d", "30d"]
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    latency_sample_limit: int = Field(ge=1)
    totals: PerformanceSummary
    by_kind: list[KindPerformanceSummary]
    by_provider: list[ProviderPerformanceSummary]


class ProviderSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    display_name: str
    kind: str
    models: list[str]
    default_model: str
    is_default: bool


class CircuitStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: Literal["closed", "open", "half_open"]
    failure_count: int = Field(ge=0)
    recovery_remaining_seconds: float | None = Field(default=None, ge=0.0)


class ProviderHealthReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    status: Literal["healthy", "degraded", "unavailable"]
    latency_ms: float | None = Field(default=None, ge=0.0)
    detail: str | None = None
    circuit: CircuitStatus | None = None


class ModelVersionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    model: str
    version: str
    status: Literal["active", "deprecated", "retired"]
    released_on: str | None = None
    notes: str | None = None
    configured: bool


class ModelVersionList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    models: list[ModelVersionItem]


class RequestLogItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(ge=1)
    request_id: str
    kind: Literal["generation", "fault_report"]
    occurred_at: datetime
    auth_role: str | None = None
    selected_provider: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_ms: float = Field(ge=0.0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    retry_count: int = Field(ge=0)
    fallback_used: bool
    fallback_reason: str | None = None
    providers_tried: list[str] = Field(default_factory=list)
    status: Literal["success", "degraded", "error"]
    error_code: str | None = None
    http_status: int = Field(ge=100, le=599)
    extraction: str | None = None
    extraction_reason: str | None = None
    missing_field_count: int | None = Field(default=None, ge=0)


class RequestLogPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[RequestLogItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
