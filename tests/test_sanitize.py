"""Credential redaction tests."""

from __future__ import annotations

from app.core.sanitize import REDACTED, sanitize


def test_sensitive_mapping_keys_are_redacted_recursively() -> None:
    payload = {
        "provider": "openai",
        "api_key": "plain-value",
        "nested": {
            "authorization": "Bearer abcdef",
            "list": [{"password": "hunter2"}, {"safe": "value"}],
        },
    }

    cleaned = sanitize(payload)

    assert cleaned["provider"] == "openai"
    assert cleaned["api_key"] == REDACTED
    assert cleaned["nested"]["authorization"] == REDACTED
    assert cleaned["nested"]["list"][0]["password"] == REDACTED
    assert cleaned["nested"]["list"][1]["safe"] == "value"
    assert payload["api_key"] == "plain-value"


def test_credential_shapes_inside_strings_are_redacted() -> None:
    message = "headers: Bearer eyJhbGciOiJIUzI1NiJ9 and key sk-abcdefgh12345"

    cleaned = sanitize(message)

    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "sk-abcdefgh12345" not in cleaned
    assert cleaned.count(REDACTED) == 2


def test_non_sensitive_values_are_unchanged() -> None:
    value = {"latency_ms": 42, "provider": "fake", "flags": [True, None]}

    assert sanitize(value) == value


def test_token_usage_metrics_are_not_redacted() -> None:
    value = {
        "prompt_tokens": 10,
        "completion_tokens": 25,
        "total_tokens": 35,
        "max_tokens": 512,
        "token_usage": {"total_tokens": 35},
    }

    assert sanitize(value) == value


def test_credential_suffix_keys_are_redacted() -> None:
    value = {
        "openai_api_key": "sk-abcdefgh12345",
        "client_secret": "value",
        "set-cookie": "session=abc",
        "private_key": "value",
    }

    cleaned = sanitize(value)

    assert set(cleaned.values()) == {REDACTED}
