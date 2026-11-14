"""Bounded SQL aggregations for cost and latency reporting."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import RequestLogRow
from app.monitoring.errors import MonitoringUnavailableError
from app.monitoring.models import (
    KindMetrics,
    LatencyMetrics,
    MonitoringAggregate,
    PerformanceMetrics,
    ProviderMetrics,
)

_AGGREGATES = (
    func.count().label("requests"),
    func.coalesce(
        func.sum(case((RequestLogRow.status == "success", 1), else_=0)), 0
    ).label("successful"),
    func.coalesce(
        func.sum(case((RequestLogRow.status == "degraded", 1), else_=0)), 0
    ).label("degraded"),
    func.coalesce(
        func.sum(case((RequestLogRow.status == "error", 1), else_=0)), 0
    ).label("errors"),
    func.coalesce(
        func.sum(
            case(
                (RequestLogRow.status.in_(("success", "degraded")), 1),
                else_=0,
            )
        ),
        0,
    ).label("accepted"),
    func.coalesce(
        func.sum(case((RequestLogRow.provider.is_not(None), 1), else_=0)), 0
    ).label("provider_requests"),
    func.coalesce(
        func.sum(
            case(
                (
                    (RequestLogRow.status == "error")
                    & RequestLogRow.provider.is_not(None),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    ).label("provider_failures"),
    func.coalesce(
        func.sum(case((RequestLogRow.fallback_used.is_(True), 1), else_=0)), 0
    ).label("fallback_requests"),
    func.coalesce(func.sum(RequestLogRow.retry_count), 0).label("retry_count"),
    func.coalesce(func.sum(RequestLogRow.prompt_tokens), 0).label("prompt_tokens"),
    func.coalesce(func.sum(RequestLogRow.completion_tokens), 0).label(
        "completion_tokens"
    ),
    func.coalesce(func.sum(RequestLogRow.total_tokens), 0).label("total_tokens"),
    func.coalesce(func.sum(RequestLogRow.cost_usd), 0).label("cost_usd"),
    func.avg(RequestLogRow.duration_ms).label("average_ms"),
    func.min(RequestLogRow.duration_ms).label("min_ms"),
    func.max(RequestLogRow.duration_ms).label("max_ms"),
)


def _as_int(value: object) -> int:
    return int(value or 0)


def _as_float(value: object) -> float:
    return float(value or 0.0)


def _as_optional_float(value: object) -> float | None:
    return None if value is None else round(float(value), 3)


def _as_decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return round(ordered[rank - 1], 3)


def _latency(
    mapping: Mapping[str, object],
    values: list[float],
    *,
    sample_truncated: bool,
) -> LatencyMetrics:
    return LatencyMetrics(
        average_ms=round(_as_float(mapping["average_ms"]), 3),
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
        min_ms=_as_optional_float(mapping["min_ms"]),
        max_ms=_as_optional_float(mapping["max_ms"]),
        sample_size=len(values),
        sample_truncated=sample_truncated,
    )


def _performance_fields(mapping: Mapping[str, object]) -> dict[str, object]:
    return {
        "requests": _as_int(mapping["requests"]),
        "accepted": _as_int(mapping["accepted"]),
        "successful": _as_int(mapping["successful"]),
        "degraded": _as_int(mapping["degraded"]),
        "errors": _as_int(mapping["errors"]),
        "provider_requests": _as_int(mapping["provider_requests"]),
        "provider_failures": _as_int(mapping["provider_failures"]),
        "fallback_requests": _as_int(mapping["fallback_requests"]),
        "retry_count": _as_int(mapping["retry_count"]),
        "prompt_tokens": _as_int(mapping["prompt_tokens"]),
        "completion_tokens": _as_int(mapping["completion_tokens"]),
        "total_tokens": _as_int(mapping["total_tokens"]),
        "cost_usd": _as_decimal(mapping["cost_usd"]),
    }


def _performance(
    mapping: Mapping[str, object], latency: LatencyMetrics
) -> PerformanceMetrics:
    return PerformanceMetrics(**_performance_fields(mapping), latency=latency)


class MonitoringRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def aggregate(
        self,
        *,
        since: datetime,
        until: datetime,
        kind: str | None = None,
        provider: str | None = None,
        sample_limit: int,
    ) -> MonitoringAggregate:
        filters = [
            RequestLogRow.occurred_at >= since,
            RequestLogRow.occurred_at <= until,
        ]
        if kind is not None:
            filters.append(RequestLogRow.kind == kind)
        if provider is not None:
            filters.append(RequestLogRow.provider == provider)

        totals_statement = select(*_AGGREGATES).where(*filters)
        kind_statement = (
            select(RequestLogRow.kind.label("group_key"), *_AGGREGATES)
            .where(*filters)
            .group_by(RequestLogRow.kind)
            .order_by(RequestLogRow.kind)
        )
        provider_statement = (
            select(RequestLogRow.provider.label("group_key"), *_AGGREGATES)
            .where(*filters, RequestLogRow.provider.is_not(None))
            .group_by(RequestLogRow.provider)
            .order_by(RequestLogRow.provider)
        )
        sample_statement = (
            select(
                RequestLogRow.kind,
                RequestLogRow.provider,
                RequestLogRow.duration_ms,
            )
            .where(*filters)
            .order_by(RequestLogRow.occurred_at.desc(), RequestLogRow.id.desc())
            .limit(sample_limit + 1)
        )

        try:
            async with self._session_factory() as session:
                totals_row = (await session.execute(totals_statement)).one()
                kind_rows = (await session.execute(kind_statement)).all()
                provider_rows = (
                    await session.execute(provider_statement)
                ).all()
                sample_rows = (await session.execute(sample_statement)).all()
        except SQLAlchemyError:
            raise MonitoringUnavailableError() from None

        sample_truncated = len(sample_rows) > sample_limit
        sampled_rows = sample_rows[:sample_limit]

        overall_values: list[float] = []
        kind_values: dict[str, list[float]] = {}
        provider_values: dict[str, list[float]] = {}
        for row in sampled_rows:
            value = max(float(row.duration_ms), 0.0)
            overall_values.append(value)
            kind_values.setdefault(row.kind, []).append(value)
            if row.provider is not None:
                provider_values.setdefault(row.provider, []).append(value)

        totals_mapping = totals_row._mapping
        totals = _performance(
            totals_mapping,
            _latency(
                totals_mapping,
                overall_values,
                sample_truncated=sample_truncated,
            ),
        )
        by_kind = tuple(
            KindMetrics(
                kind=row.group_key,
                latency=_latency(
                    row._mapping,
                    kind_values.get(row.group_key, []),
                    sample_truncated=sample_truncated,
                ),
                **_performance_fields(row._mapping),
            )
            for row in kind_rows
        )
        by_provider = tuple(
            ProviderMetrics(
                provider=row.group_key,
                latency=_latency(
                    row._mapping,
                    provider_values.get(row.group_key, []),
                    sample_truncated=sample_truncated,
                ),
                **_performance_fields(row._mapping),
            )
            for row in provider_rows
        )
        return MonitoringAggregate(
            totals=totals,
            by_kind=by_kind,
            by_provider=by_provider,
        )
