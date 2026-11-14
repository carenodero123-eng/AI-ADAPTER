"""Normalized provider schema validation tests."""

from __future__ import annotations

import pytest
from app.providers.schemas import (
    ChatMessage,
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from pydantic import ValidationError


def test_message_content_is_stripped() -> None:
    message = ChatMessage(role="user", content="  overheating  ")

    assert message.content == "overheating"


def test_blank_message_content_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="   ")


def test_generation_request_requires_messages() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(model="fake-small", messages=[])


def test_generation_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            model="fake-small",
            messages=[{"role": "user", "content": "hello"}],
            prompt="unexpected",
        )


def test_token_usage_total_must_match_parts() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=99)


def test_generation_result_has_normalized_shape() -> None:
    result = GenerationResult(
        provider="fake",
        model="fake-small",
        content="ok",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        latency_ms=0.5,
    )

    assert result.finish_reason == "stop"
    assert result.model_dump()["usage"]["total_tokens"] == 2
