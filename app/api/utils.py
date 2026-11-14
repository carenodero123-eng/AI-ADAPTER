"""Small helpers shared by API routes."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from starlette.requests import Request


def uptime_seconds(request: Request) -> float:
    started_at: datetime = request.app.state.started_at
    return round((datetime.now(UTC) - started_at).total_seconds(), 3)


def elapsed_ms(request: Request) -> float:
    started = getattr(request.state, "request_started_perf", None)
    if started is None:
        return 0.0
    return round((time.perf_counter() - started) * 1000, 2)

