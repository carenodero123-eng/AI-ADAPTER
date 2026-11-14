"""Map API paths to the persisted request kinds."""

from __future__ import annotations

from app.database.records import RequestLogKind


def request_kind_for_path(path: str) -> RequestLogKind | None:
    normalized = path.rstrip("/")
    if normalized.endswith("/fault-reports/summarize"):
        return "fault_report"
    if normalized.endswith("/generate"):
        return "generation"
    return None
