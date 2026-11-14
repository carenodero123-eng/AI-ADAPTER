"""Authentication, authorization, and rate-limit errors."""

from __future__ import annotations

import math

from app.core.errors import ApplicationError


class AuthenticationRequiredError(ApplicationError):
    code = "authentication_required"
    status_code = 401
    retryable = False

    def __init__(self) -> None:
        super().__init__(
            "A valid API key is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class PermissionDeniedError(ApplicationError):
    code = "permission_denied"
    status_code = 403
    retryable = False

    def __init__(self) -> None:
        super().__init__("Administrator privileges are required.")


class RateLimitExceededError(ApplicationError):
    code = "rate_limit_exceeded"
    status_code = 429
    retryable = True

    def __init__(self, *, retry_after_seconds: float, limit: int) -> None:
        retry_after = max(1, math.ceil(retry_after_seconds))
        super().__init__(
            f"Rate limit exceeded; retry after {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
        self.retry_after_seconds = retry_after
