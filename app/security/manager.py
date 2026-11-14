"""API key authentication with constant-time comparison."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable

from app.security.models import AuthIdentity


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SecurityManager:
    """Resolve bearer tokens to roles without retaining raw keys.

    Only SHA-256 digests are held in memory after construction. Comparisons use
    ``secrets.compare_digest`` so token verification does not leak timing.
    """

    def __init__(
        self,
        *,
        user_keys: Iterable[str] = (),
        admin_keys: Iterable[str] = (),
    ) -> None:
        self._admin_digests = tuple(_digest(key) for key in admin_keys)
        self._user_digests = tuple(_digest(key) for key in user_keys)

    @property
    def user_key_count(self) -> int:
        return len(self._user_digests)

    @property
    def admin_key_count(self) -> int:
        return len(self._admin_digests)

    def authenticate(self, token: str) -> AuthIdentity | None:
        if not token:
            return None

        digest = _digest(token)
        if any(secrets.compare_digest(digest, known) for known in self._admin_digests):
            return AuthIdentity(role="admin", rate_limit_key=f"key:{digest[:16]}")
        if any(secrets.compare_digest(digest, known) for known in self._user_digests):
            return AuthIdentity(role="user", rate_limit_key=f"key:{digest[:16]}")
        return None
