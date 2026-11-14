"""Authenticated identity representation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthRole = Literal["anonymous", "user", "admin"]


@dataclass(frozen=True)
class AuthIdentity:
    """An authenticated caller without any raw credential material."""

    role: AuthRole
    rate_limit_key: str
