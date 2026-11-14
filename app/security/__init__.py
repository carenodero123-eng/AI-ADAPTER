"""Authentication, authorization, and rate limiting."""

from app.core.errors import ApplicationError
from app.security.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    RateLimitExceededError,
)
from app.security.manager import SecurityManager
from app.security.models import AuthIdentity
from app.security.rate_limit import RateLimitDecision, RateLimiter

__all__ = [
    "ApplicationError",
    "AuthIdentity",
    "AuthenticationRequiredError",
    "PermissionDeniedError",
    "RateLimitDecision",
    "RateLimitExceededError",
    "RateLimiter",
    "SecurityManager",
]
