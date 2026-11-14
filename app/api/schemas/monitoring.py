"""Administrative cost and latency reporting response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.monitoring.models import (
    KindMetrics,
    LatencyMetrics,
    PerformanceMetrics,
    ProviderMetrics,
)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _usd(value: float) -> float:
    return round(max(value, 0.0), 9)


class LatencySummary(BaseModel):
    average_ms: float = Field(ge=0.0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    min_ms: float | None = Field(default=None, ge=0.0)
    max_ms: float | None = Field(default=None, ge=0.0)
    sample_size: int = Field(ge=0)
    sample_truncated: bool


class PerformanceSummary(BaseModel):
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
    provider: str = Field(min_length=1, max_length=32)


class MonitoringSummary(BaseModel):
    window: Literal["15m", "1h", "6h", "24h", "7d", "30d"]
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    latency_sample_limit: int = Field(ge=1)
    totals: PerformanceSummary
    by_kind: list[KindPerformanceSummary]
    by_provider: list[ProviderPerformanceSummary]


def _latency_summary(latency: LatencyMetrics) -> LatencySummary:
    return LatencySummary(
        average_ms=latency.average_ms,
        p50_ms=latency.p50_ms,
        p95_ms=latency.p95_ms,
        min_ms=latency.min_ms,
        max_ms=latency.max_ms,
        sample_size=latency.sample_size,
        sample_truncated=latency.sample_truncated,
    )


def _performance_fields(metrics: PerformanceMetrics) -> dict[str, object]:
    cost = float(metrics.cost_usd)
    return {
        "requests": metrics.requests,
        "accepted": metrics.accepted,
        "successful": metrics.successful,
        "degraded": metrics.degraded,
        "errors": metrics.errors,
        "accepted_rate": _rate(metrics.accepted, metrics.requests),
        "success_rate": _rate(metrics.successful, metrics.requests),
        "degraded_rate": _rate(metrics.degraded, metrics.requests),
        "error_rate": _rate(metrics.errors, metrics.requests),
        "provider_requests": metrics.provider_requests,
        "provider_failures": metrics.provider_failures,
        "provider_failure_rate": _rate(
            metrics.provider_failures, metrics.provider_requests
        ),
        "fallback_requests": metrics.fallback_requests,
        "fallback_rate": _rate(metrics.fallback_requests, metrics.requests),
        "retry_count": metrics.retry_count,
        "prompt_tokens": metrics.prompt_tokens,
        "completion_tokens": metrics.completion_tokens,
        "total_tokens": metrics.total_tokens,
        "cost_usd": _usd(cost),
        "cost_per_request_usd": _usd(
            cost / metrics.requests if metrics.requests else 0.0
        ),
        "cost_per_accepted_result_usd": _usd(
            cost / metrics.accepted if metrics.accepted else 0.0
        ),
        "latency": _latency_summary(metrics.latency),
    }


def performance_summary(metrics: PerformanceMetrics) -> PerformanceSummary:
    return PerformanceSummary(**_performance_fields(metrics))


def kind_summary(metrics: KindMetrics) -> KindPerformanceSummary:
    return KindPerformanceSummary(
        kind=metrics.kind, **_performance_fields(metrics)
    )


def provider_summary(metrics: ProviderMetrics) -> ProviderPerformanceSummary:
    return ProviderPerformanceSummary(
        provider=metrics.provider, **_performance_fields(metrics)
    )
