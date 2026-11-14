"""Logging configuration and JSON formatter tests."""

from __future__ import annotations

import json
import logging

from app.core.config import Settings
from app.core.logging import JsonFormatter, configure_logging


def test_json_formatter_is_parseable_and_redacts() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="call failed with key sk-abcdefgh12345",
        args=(),
        exc_info=None,
    )
    record.event = "provider.call"
    record.authorization = "Bearer super-secret-token"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "provider.call"
    assert payload["logger"] == "app.test"
    assert payload["authorization"] == "[REDACTED]"
    assert "sk-abcdefgh12345" not in payload["message"]


def test_configure_logging_is_idempotent(settings: Settings) -> None:
    configure_logging(settings)
    configure_logging(settings)

    tagged = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_ai_adapter_handler", False)
    ]
    assert len(tagged) == 1
