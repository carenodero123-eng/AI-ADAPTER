"""Safe public errors raised by the persistence layer."""

from __future__ import annotations

from app.core.errors import ApplicationError


class PersistenceUnavailableError(ApplicationError):
    code = "persistence_unavailable"
    status_code = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Request history is temporarily unavailable.")


class RequestLogNotFoundError(ApplicationError):
    code = "request_log_not_found"
    status_code = 404
    retryable = False

    def __init__(self) -> None:
        super().__init__("The requested log record does not exist.")


class InvalidRequestLogFilterError(ApplicationError):
    code = "invalid_request_filter"
    status_code = 422
    retryable = False

    def __init__(self) -> None:
        super().__init__("The 'since' filter must not be later than 'until'.")
