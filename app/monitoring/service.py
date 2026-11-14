"""Windowed monitoring reports built from persisted request logs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta

from app.database.records import RequestLogKind, as_utc, utc_now
from app.monitoring.errors import MonitoringUnavailableError
from app.monitoring.models import (
    MonitoringReport,
    MonitoringWindow,
)
from app.monitoring.repository import MonitoringRepository

WINDOW_DURATIONS: dict[MonitoringWindow, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class MonitoringService:
    """Read bounded aggregates without exposing individual prompts or keys."""

    def __init__(
        self,
        repository: MonitoringRepository | None,
        *,
        timeout_seconds: float,
        sample_limit: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if sample_limit < 1:
            raise ValueError("sample_limit must be at least 1")
        self._repository = repository
        self._timeout_seconds = timeout_seconds
        self._sample_limit = sample_limit
        self._clock = clock

    @property
    def enabled(self) -> bool:
        return self._repository is not None

    async def summary(
        self,
        *,
        window: MonitoringWindow,
        kind: RequestLogKind | None = None,
        provider: str | None = None,
    ) -> MonitoringReport:
        repository = self._require_repository()
        generated_at = as_utc(self._clock())
        window_start = generated_at - WINDOW_DURATIONS[window]
        try:
            async with asyncio.timeout(self._timeout_seconds):
                aggregate = await repository.aggregate(
                    since=window_start,
                    until=generated_at,
                    kind=kind,
                    provider=provider,
                    sample_limit=self._sample_limit,
                )
        except TimeoutError:
            raise MonitoringUnavailableError() from None

        return MonitoringReport(
            window=window,
            window_start=window_start,
            window_end=generated_at,
            generated_at=generated_at,
            latency_sample_limit=self._sample_limit,
            totals=aggregate.totals,
            by_kind=aggregate.by_kind,
            by_provider=aggregate.by_provider,
        )

    def _require_repository(self) -> MonitoringRepository:
        if self._repository is None:
            raise MonitoringUnavailableError()
        return self._repository
