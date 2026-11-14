"""Safe request-log recording and query facade."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from app.database.errors import PersistenceUnavailableError
from app.database.records import (
    RequestLogEntry,
    RequestLogKind,
    RequestLogStatus,
    StoredRequestLog,
)
from app.database.repository import RequestLogRepository

logger = logging.getLogger("app.persistence")


class RequestLogService:
    """Record requests without ever failing the caller on persistence errors."""

    def __init__(
        self,
        repository: RequestLogRepository | None,
        *,
        timeout_seconds: float,
        observer: Callable[[RequestLogEntry], None] | None = None,
    ) -> None:
        self._repository = repository
        self._timeout_seconds = timeout_seconds
        self._observer = observer

    @property
    def enabled(self) -> bool:
        return self._repository is not None

    async def record(self, entry: RequestLogEntry) -> bool:
        self._observe(entry)
        if self._repository is None:
            return False
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._repository.add(entry)
        except Exception as error:  # persistence must never break the API
            logger.warning(
                "request_log.persist_failed",
                extra={
                    "event": "request_log.persist_failed",
                    "request_id": entry.request_id,
                    "kind": entry.kind,
                    "error_type": type(error).__name__,
                },
            )
            return False
        return True

    async def list_entries(
        self,
        *,
        kind: RequestLogKind | None = None,
        status: RequestLogStatus | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[StoredRequestLog], int]:
        repository = self._require_repository()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await repository.list_entries(
                    kind=kind,
                    status=status,
                    provider=provider,
                    since=since,
                    until=until,
                    limit=limit,
                    offset=offset,
                )
        except TimeoutError:
            raise PersistenceUnavailableError() from None

    async def get(self, record_id: int) -> StoredRequestLog | None:
        repository = self._require_repository()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await repository.get(record_id)
        except TimeoutError:
            raise PersistenceUnavailableError() from None

    async def ping(self) -> bool:
        if self._repository is None:
            return False
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._repository.ping()
        except Exception as error:
            logger.warning(
                "request_log.ping_failed",
                extra={
                    "event": "request_log.ping_failed",
                    "error_type": type(error).__name__,
                },
            )
            return False
        return True

    def _require_repository(self) -> RequestLogRepository:
        if self._repository is None:
            raise PersistenceUnavailableError()
        return self._repository

    def _observe(self, entry: RequestLogEntry) -> None:
        if self._observer is None:
            return
        try:
            self._observer(entry)
        except Exception as error:  # metrics must never break the API
            logger.warning(
                "request_log.metrics_failed",
                extra={
                    "event": "request_log.metrics_failed",
                    "request_id": entry.request_id,
                    "kind": entry.kind,
                    "error_type": type(error).__name__,
                },
            )
