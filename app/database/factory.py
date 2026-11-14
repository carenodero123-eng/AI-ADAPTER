"""Factory helpers for database-backed request logging."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.database.engine import DatabaseManager
from app.database.records import RequestLogEntry
from app.database.repository import RequestLogRepository
from app.database.service import RequestLogService


def build_database(settings: Settings) -> DatabaseManager | None:
    if not settings.database_enabled:
        return None
    return DatabaseManager(
        settings.database_dsn,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        auto_create=settings.database_auto_create,
    )


def build_request_log_service(
    settings: Settings,
    database: DatabaseManager | None,
    *,
    observer: Callable[[RequestLogEntry], None] | None = None,
) -> RequestLogService:
    repository = (
        RequestLogRepository(database.session_factory)
        if database is not None
        else None
    )
    return RequestLogService(
        repository,
        timeout_seconds=settings.database_write_timeout_seconds,
        observer=observer,
    )
