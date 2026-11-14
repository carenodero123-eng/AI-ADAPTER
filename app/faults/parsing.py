"""Parse and validate AI-produced fault summaries."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import ValidationError

from app.faults.models import FaultSummary

ParseFailureReason = Literal["ai_invalid_json", "ai_invalid_schema"]


class FaultSummaryParseError(Exception):
    """AI output could not be decoded into the validated summary contract."""

    def __init__(self, reason: ParseFailureReason) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_fault_summary(content: str) -> FaultSummary:
    """Decode strict JSON from a provider response and validate it.

    Models occasionally wrap JSON in markdown fences or add prose. The parser
    locates the first complete object; schema validation remains strict and
    unknown keys are rejected.
    """

    text = content.strip()
    if not text:
        raise FaultSummaryParseError("ai_invalid_json")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise FaultSummaryParseError("ai_invalid_json")

    try:
        payload = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError) as error:
        raise FaultSummaryParseError("ai_invalid_json") from error

    if not isinstance(payload, dict):
        raise FaultSummaryParseError("ai_invalid_json")

    try:
        return FaultSummary.model_validate(payload)
    except ValidationError as error:
        raise FaultSummaryParseError("ai_invalid_schema") from error
