"""Framework-neutral monitoring report records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

MonitoringWindow = Literal["15m", "1h", "6h", "24h", "7d", "30d"]


@dataclass(frozen=True, slots=True)
class LatencyMetrics:
    average_ms: float
    p50_ms: float | None
    p95_ms: float | None
    min_ms: float | None
    max_ms: float | None
    sample_size: int
    sample_truncated: bool


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    requests: int
    accepted: int
    successful: int
    degraded: int
    errors: int
    provider_requests: int
    provider_failures: int
    fallback_requests: int
    retry_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Decimal
    latency: LatencyMetrics


@dataclass(frozen=True, slots=True)
class KindMetrics(PerformanceMetrics):
    kind: str


@dataclass(frozen=True, slots=True)
class ProviderMetrics(PerformanceMetrics):
    provider: str


@dataclass(frozen=True, slots=True)
class MonitoringAggregate:
    totals: PerformanceMetrics
    by_kind: tuple[KindMetrics, ...]
    by_provider: tuple[ProviderMetrics, ...]


@dataclass(frozen=True, slots=True)
class MonitoringReport:
    window: MonitoringWindow
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    latency_sample_limit: int
    totals: PerformanceMetrics
    by_kind: tuple[KindMetrics, ...]
    by_provider: tuple[ProviderMetrics, ...]
