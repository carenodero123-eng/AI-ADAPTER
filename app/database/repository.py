"""Persistence operations for request logs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.errors import PersistenceUnavailableError
from app.database.models import RequestLogRow
from app.database.records import (
    RequestLogEntry,
    RequestLogKind,
    RequestLogStatus,
    StoredRequestLog,
    as_utc,
)


def _to_record(row: RequestLogRow) -> StoredRequestLog:
    return StoredRequestLog(
        id=row.id,
        request_id=row.request_id,
        kind=cast(RequestLogKind, row.kind),
        occurred_at=as_utc(row.occurred_at),
        auth_role=row.auth_role,
        selected_provider=row.selected_provider,
        provider=row.provider,
        model=row.model,
        duration_ms=row.duration_ms,
        prompt_tokens=row.prompt_tokens or 0,
        completion_tokens=row.completion_tokens or 0,
        total_tokens=row.total_tokens or 0,
        cost_usd=Decimal(str(row.cost_usd or "0")),
        retry_count=row.retry_count or 0,
        fallback_used=bool(row.fallback_used),
        fallback_reason=row.fallback_reason,
        providers_tried=tuple(row.providers_tried or ()),
        status=cast(RequestLogStatus, row.status),
        error_code=row.error_code,
        http_status=row.http_status,
        extraction=row.extraction,
        extraction_reason=row.extraction_reason,
        missing_field_count=row.missing_field_count,
    )


class RequestLogRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def add(self, entry: RequestLogEntry) -> int:
        row = RequestLogRow(
            request_id=entry.request_id,
            kind=entry.kind,
            occurred_at=entry.occurred_at,
            auth_role=entry.auth_role,
            selected_provider=entry.selected_provider,
            provider=entry.provider,
            model=entry.model,
            duration_ms=entry.duration_ms,
            prompt_tokens=entry.prompt_tokens,
            completion_tokens=entry.completion_tokens,
            total_tokens=entry.total_tokens,
            cost_usd=entry.cost_usd,
            retry_count=entry.retry_count,
            fallback_used=entry.fallback_used,
            fallback_reason=entry.fallback_reason,
            providers_tried=list(entry.providers_tried),
            status=entry.status,
            error_code=entry.error_code,
            http_status=entry.http_status,
            extraction=entry.extraction,
            extraction_reason=entry.extraction_reason,
            missing_field_count=entry.missing_field_count,
        )
        try:
            async with self._session_factory() as session:
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return row.id
        except SQLAlchemyError:
            raise PersistenceUnavailableError() from None

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
        filters = []
        if kind is not None:
            filters.append(RequestLogRow.kind == kind)
        if status is not None:
            filters.append(RequestLogRow.status == status)
        if provider is not None:
            filters.append(RequestLogRow.provider == provider)
        if since is not None:
            filters.append(RequestLogRow.occurred_at >= as_utc(since))
        if until is not None:
            filters.append(RequestLogRow.occurred_at <= as_utc(until))

        statement = select(RequestLogRow).order_by(
            RequestLogRow.occurred_at.desc(), RequestLogRow.id.desc()
        )
        count_statement = select(func.count()).select_from(RequestLogRow)
        if filters:
            statement = statement.where(*filters)
            count_statement = count_statement.where(*filters)

        try:
            async with self._session_factory() as session:
                rows = (
                    await session.execute(statement.limit(limit).offset(offset))
                ).scalars()
                total = int(
                    (await session.execute(count_statement)).scalar_one()
                )
                return [_to_record(row) for row in rows], total
        except SQLAlchemyError:
            raise PersistenceUnavailableError() from None

    async def get(self, record_id: int) -> StoredRequestLog | None:
        try:
            async with self._session_factory() as session:
                row = await session.get(RequestLogRow, record_id)
                return _to_record(row) if row is not None else None
        except SQLAlchemyError:
            raise PersistenceUnavailableError() from None

    async def ping(self) -> None:
        try:
            async with self._session_factory() as session:
                await session.execute(
                    text("SELECT 1 FROM request_logs LIMIT 1")
                )
        except SQLAlchemyError:
            raise PersistenceUnavailableError() from None
