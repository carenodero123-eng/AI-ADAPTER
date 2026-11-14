"""Application-level errors shared by security and budget components."""

from __future__ import annotations

from collections.abc import Mapping


class ApplicationError(Exception):
    """Base class for non-provider failures with a safe public contract."""

    code = "application_error"
    status_code = 500
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.headers = dict(headers or {})
