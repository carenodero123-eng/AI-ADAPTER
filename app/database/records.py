"""Framework-neutral request-log records shared by services and routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

RequestLogKind = Literal["generation", "fault_report"]
RequestLogStatus = Literal["success", "degraded", "error"]

_ZERO = Decimal("0.000000")


@dataclass(frozen=True, slots=True)
class RequestLogEntry:
    request_id: str
    kind: RequestLogKind
    occurred_at: datetime
    auth_role: str | None
    selected_provider: str | None
    provider: str | None
    model: str | None
    duration_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal = _ZERO
    retry_count: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    providers_tried: tuple[str, ...] = field(default_factory=tuple)
    status: RequestLogStatus = "success"
    error_code: str | None = None
    http_status: int = 200
    extraction: str | None = None
    extraction_reason: str | None = None
    missing_field_count: int | None = None


@dataclass(frozen=True, slots=True)
class StoredRequestLog(RequestLogEntry):
    id: int = 0


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
