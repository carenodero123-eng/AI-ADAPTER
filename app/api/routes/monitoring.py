"""Administrator-only cost, latency, and Prometheus monitoring."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.api.deps import AdminDep, MetricsCollectorDep, MonitoringServiceDep
from app.api.errors import (
    MONITORING_ERROR_RESPONSES,
    SECURITY_ERROR_RESPONSES,
)
from app.api.schemas.monitoring import (
    MonitoringSummary,
    kind_summary,
    performance_summary,
    provider_summary,
)
from app.database.records import RequestLogKind
from app.monitoring.metrics import METRICS_CONTENT_TYPE
from app.monitoring.models import MonitoringWindow

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get(
    "/summary",
    response_model=MonitoringSummary,
    responses={**SECURITY_ERROR_RESPONSES, **MONITORING_ERROR_RESPONSES},
    summary="Cost and latency report",
)
async def monitoring_summary(
    _admin: AdminDep,
    service: MonitoringServiceDep,
    window: MonitoringWindow = Query(default="24h"),
    kind: RequestLogKind | None = Query(default=None),
    provider: str | None = Query(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
        max_length=32,
    ),
) -> MonitoringSummary:
    report = await service.summary(
        window=window,
        kind=kind,
        provider=provider,
    )
    return MonitoringSummary(
        window=report.window,
        window_start=report.window_start,
        window_end=report.window_end,
        generated_at=report.generated_at,
        latency_sample_limit=report.latency_sample_limit,
        totals=performance_summary(report.totals),
        by_kind=[kind_summary(metrics) for metrics in report.by_kind],
        by_provider=[
            provider_summary(metrics) for metrics in report.by_provider
        ],
    )


@router.get(
    "/metrics",
    response_class=Response,
    responses={
        **SECURITY_ERROR_RESPONSES,
        200: {
            "content": {"text/plain": {"schema": {"type": "string"}}},
            "description": "Prometheus text exposition",
        },
    },
    summary="Prometheus metrics",
)
async def prometheus_metrics(
    _admin: AdminDep,
    collector: MetricsCollectorDep,
) -> Response:
    return Response(
        content=collector.render(),
        media_type=METRICS_CONTENT_TYPE,
    )
