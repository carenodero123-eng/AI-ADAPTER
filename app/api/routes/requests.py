"""Administrator-only persisted request history."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import AdminDep, RequestLogServiceDep
from app.api.errors import PERSISTENCE_ERROR_RESPONSES, SECURITY_ERROR_RESPONSES
from app.api.schemas.requests import RequestLogItem, RequestLogPage
from app.database.errors import (
    InvalidRequestLogFilterError,
    RequestLogNotFoundError,
)
from app.database.records import as_utc

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get(
    "",
    response_model=RequestLogPage,
    responses={**SECURITY_ERROR_RESPONSES, **PERSISTENCE_ERROR_RESPONSES},
    summary="List persisted AI requests",
)
async def list_request_logs(
    _admin: AdminDep,
    service: RequestLogServiceDep,
    kind: Literal["generation", "fault_report"] | None = Query(default=None),
    status: Literal["success", "degraded", "error"] | None = Query(default=None),
    provider: str | None = Query(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
        max_length=32,
    ),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RequestLogPage:
    since_utc = as_utc(since) if since is not None else None
    until_utc = as_utc(until) if until is not None else None
    if (
        since_utc is not None
        and until_utc is not None
        and since_utc > until_utc
    ):
        raise InvalidRequestLogFilterError()

    entries, total = await service.list_entries(
        kind=kind,
        status=status,
        provider=provider,
        since=since_utc,
        until=until_utc,
        limit=limit,
        offset=offset,
    )
    return RequestLogPage(
        items=[RequestLogItem.model_validate(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{record_id}",
    response_model=RequestLogItem,
    responses={**SECURITY_ERROR_RESPONSES, **PERSISTENCE_ERROR_RESPONSES},
    summary="Get one persisted AI request",
)
async def get_request_log(
    record_id: Annotated[int, Path(ge=1)],
    _admin: AdminDep,
    service: RequestLogServiceDep,
) -> RequestLogItem:
    entry = await service.get(record_id)
    if entry is None:
        raise RequestLogNotFoundError()
    return RequestLogItem.model_validate(entry)
