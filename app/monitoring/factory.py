"""Factory helpers for monitoring reports and metrics."""

from __future__ import annotations

from app.core.config import Settings
from app.database.engine import DatabaseManager
from app.monitoring.metrics import MetricsCollector
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import MonitoringService


def build_monitoring_service(
    settings: Settings, database: DatabaseManager | None
) -> MonitoringService:
    repository = (
        MonitoringRepository(database.session_factory)
        if database is not None
        else None
    )
    return MonitoringService(
        repository,
        timeout_seconds=settings.monitoring_query_timeout_seconds,
        sample_limit=settings.monitoring_latency_sample_limit,
    )


def build_metrics_collector() -> MetricsCollector:
    return MetricsCollector()
