"""Safe public errors raised by monitoring reports."""

from __future__ import annotations

from app.core.errors import ApplicationError


class MonitoringUnavailableError(ApplicationError):
    code = "monitoring_unavailable"
    status_code = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Cost and latency monitoring is temporarily unavailable.")
