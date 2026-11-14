"""Deterministic token estimation used for budget reservations."""

from __future__ import annotations

from collections.abc import Sequence

from app.providers.schemas import ChatMessage


def estimate_prompt_tokens(messages: Sequence[ChatMessage]) -> int:
    """Approximate prompt tokens without a vendor tokenizer.

    The estimate is intentionally conservative: four characters per token plus
    per-message overhead. Reservations only need a stable upper-ish bound, while
    settled cost uses provider-reported usage.
    """

    return sum(
        max(1, (len(message.content) + 3) // 4) + 4
        for message in messages
    )
