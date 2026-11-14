"""Redaction helpers used before anything is written to logs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|auth[_-]?token|bearer[_-]?token|token|secret|secret[_-]?key|"
    r"private[_-]?key|client[_-]?secret|password|passwd|cookie|credentials?)$",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def sanitize(value: Any, key: str | None = None) -> Any:
    """Recursively redact sensitive mapping keys and credential-shaped strings.

    The function never mutates its input and is safe to apply to arbitrary log
    payloads, including nested dictionaries and sequences.
    """

    if key is not None and _SENSITIVE_KEY.search(key):
        return REDACTED

    if isinstance(value, Mapping):
        return {str(item_key): sanitize(item, str(item_key)) for item_key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize(item) for item in value]

    if isinstance(value, str):
        value = _BEARER.sub(r"\1" + REDACTED, value)
        value = _OPENAI_KEY.sub(REDACTED, value)
        return value

    return value
