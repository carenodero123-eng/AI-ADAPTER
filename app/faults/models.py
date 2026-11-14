"""Validated structured output for the industrial fault-report summarizer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FaultSeverity = Literal["low", "medium", "high", "critical"]
TemperatureUnit = Literal["C", "F"]
ExtractionMode = Literal["provider", "deterministic"]

SUMMARY_FIELDS = (
    "machine",
    "fault_description",
    "temperature",
    "downtime",
    "action_taken",
    "severity",
)

_SEVERITY_ALIASES = {
    "low": "low",
    "minor": "low",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "high": "high",
    "major": "high",
    "critical": "critical",
    "crit": "critical",
}

_UNIT_ALIASES = {
    "C": "C",
    "CELSIUS": "C",
    "\u00b0C": "C",
    "F": "F",
    "FAHRENHEIT": "F",
    "\u00b0F": "F",
}


class FaultSummary(BaseModel):
    """The only shape returned to callers for extracted fault data.

    Missing values stay ``None``. The deterministic extractor and the AI
    prompt both follow this rule instead of inventing plausible values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    machine: str | None = Field(default=None, max_length=120)
    fault_description: str | None = Field(default=None, max_length=500)
    temperature: float | None = Field(default=None, allow_inf_nan=False)
    temperature_unit: TemperatureUnit | None = None
    downtime: str | None = Field(default=None, max_length=80)
    action_taken: str | None = Field(default=None, max_length=500)
    severity: FaultSeverity | None = None

    @field_validator(
        "machine", "fault_description", "downtime", "action_taken", mode="before"
    )
    @classmethod
    def _clean_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split()).strip().strip("\"'")
        normalized = normalized.rstrip(".;,")
        return normalized or None

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().lower()
        return _SEVERITY_ALIASES.get(token, token) if token else None

    @field_validator("temperature_unit", mode="before")
    @classmethod
    def _normalize_unit(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().upper()
        return _UNIT_ALIASES.get(token, token) if token else None

    @model_validator(mode="after")
    def _unit_requires_temperature(self) -> FaultSummary:
        if self.temperature is None and self.temperature_unit is not None:
            raise ValueError("temperature_unit requires temperature")
        return self


def summarize_fields(summary: FaultSummary) -> tuple[str, ...]:
    """Return the required fields that remain unknown."""

    return tuple(
        field for field in SUMMARY_FIELDS if getattr(summary, field) is None
    )


def is_empty_summary(summary: FaultSummary) -> bool:
    """True when no required field carries information."""

    return all(getattr(summary, field) is None for field in SUMMARY_FIELDS)
