"""Build security components from validated settings."""

from __future__ import annotations

from app.core.config import Settings
from app.security.manager import SecurityManager
from app.security.rate_limit import RateLimiter


def build_security_manager(settings: Settings) -> SecurityManager:
    return SecurityManager(
        user_keys=settings.security_api_key_list,
        admin_keys=settings.security_admin_key_list,
    )


def build_rate_limiter(settings: Settings) -> RateLimiter:
    return RateLimiter(
        max_requests=settings.security_rate_limit_requests,
        window_seconds=settings.security_rate_limit_window_seconds,
    )
