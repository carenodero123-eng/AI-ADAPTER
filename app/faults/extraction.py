"""Deterministic rule-based extraction for the fault-report fallback path.

The extractor only returns values that appear explicitly in the report.
Anything it cannot find remains ``None``; it never fills a plausible default.
"""

from __future__ import annotations

import re

from app.faults.models import FaultSeverity, FaultSummary, TemperatureUnit

_UNKNOWN_VALUES = {
    "-",
    "",
    "n/a",
    "na",
    "no",
    "no action",
    "no action taken",
    "no downtime",
    "none",
    "not available",
    "not down",
    "not specified",
    "null",
    "pending",
    "required",
    "tbd",
    "to be determined",
    "unknown",
}

_LABEL_LINE = re.compile(
    r"(?im)^\s*([A-Za-z][A-Za-z /_-]{0,40}?)\s*[:\-]\s*(.+?)\s*$"
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_LEADING_LABEL = re.compile(r"^[A-Za-z][A-Za-z /_-]{0,40}?\s*[:\-]\s*")
_DURATION = re.compile(
    r"(?i)(\d+(?:\.\d+)?)\s*"
    r"(minutes?|mins?|min|m|hours?|hrs?|hr|h|days?|d|shifts?)\b"
)
_TEMPERATURE = re.compile(
    r"(?i)(-?\d+(?:\.\d+)?)\s*"
    r"(?:\u00b0\s*|degrees?\s*)?(celsius|fahrenheit|c|f)\b"
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_EQUIPMENT = re.compile(
    r"(?i)\b(pump|conveyor|compressor|motor|turbine|boiler|valve|fan|"
    r"gearbox|generator|cnc|robot|press|mixer|blower|chiller|furnace)"
    r"\s*(?:no\.?|#)?\s*([a-z]?\d+[a-z0-9-]*)\b"
)

_FAULT_KEYWORDS = (
    "fault",
    "failure",
    "failed",
    "overheat",
    "vibration",
    "leak",
    "noise",
    "smoke",
    "jam",
    "stopped",
    "broken",
    "crack",
    "wear",
    "misalign",
    "blocked",
    "seized",
    "alarm",
    "error",
    "temperature",
)

_ACTION_KEYWORDS = (
    "replaced",
    "adjusted",
    "reset",
    "cleaned",
    "lubricated",
    "repaired",
    "tightened",
    "recalibrated",
    "installed",
    "swapped",
    "realigned",
    "restarted",
)

_CRITICAL_SIGNALS = (
    "fire",
    "explosion",
    "injury",
    "fatality",
    "safety hazard",
    "toxic",
    "collapse",
    "electrocution",
    "emergency shutdown",
)
_HIGH_SIGNALS = (
    "overheat",
    "overheating",
    "smoke",
    "severe vibration",
    "production stopped",
    "line stopped",
    "failure",
    "seized",
    "broken",
    "jam",
    "high temperature",
)
_MEDIUM_SIGNALS = (
    "vibration",
    "abnormal noise",
    "leak",
    "wear",
    "degradation",
    "intermittent",
    "temperature alarm",
    "temperature rise",
)
_LOW_SIGNALS = (
    "minor",
    "cosmetic",
    "no production impact",
    "scheduled maintenance",
)


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip().strip("\"'")
    normalized = normalized.rstrip(".;,")
    if not normalized or normalized.lower() in _UNKNOWN_VALUES:
        return None
    return normalized[:limit].rstrip() or None


def _parse_labels(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for match in _LABEL_LINE.finditer(text):
        label = " ".join(match.group(1).strip().lower().split())
        labels.setdefault(label, match.group(2).strip())
    return labels


def _find_labeled(
    labels: dict[str, str], text: str, names: tuple[str, ...]
) -> str | None:
    for name in names:
        value = labels.get(name)
        if value is not None:
            return value
    for name in names:
        match = re.search(
            rf"(?i)\b{re.escape(name)}\b\s*[:\-]\s*([^.;\n]+)", text
        )
        if match is not None:
            return match.group(1)
    return None


def _first_sentence_with(
    text: str, keywords: tuple[str, ...], limit: int
) -> str | None:
    for sentence in _SENTENCE_SPLIT.split(text):
        candidate = sentence.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(keyword in lowered for keyword in keywords):
            return _clean(_LEADING_LABEL.sub("", candidate), limit)
    return None


def _number_text(value: str) -> str:
    return f"{float(value):g}"


def _duration_text(number: str, unit: str) -> str:
    lowered = unit.lower()
    if lowered.startswith("min") or lowered == "m":
        base = "minute"
    elif lowered.startswith("h"):
        base = "hour"
    elif lowered.startswith("d"):
        base = "day"
    else:
        base = "shift"
    amount = float(number)
    return f"{amount:g} {base if amount == 1 else base + 's'}"


def _duration_from_match(match: re.Match[str]) -> str:
    return _duration_text(match.group(1), match.group(2))


def _unit(value: str) -> TemperatureUnit:
    return "C" if value.lower().startswith("c") else "F"


def _temperature(raw: str | None, text: str) -> tuple[float | None, TemperatureUnit | None]:
    if raw is not None:
        match = _TEMPERATURE.search(raw)
        if match is not None:
            return float(match.group(1)), _unit(match.group(2))
        match = _NUMBER.search(raw)
        if match is not None:
            return float(match.group(0)), None

    match = _TEMPERATURE.search(text)
    if match is not None:
        return float(match.group(1)), _unit(match.group(2))
    return None, None


def _downtime(raw: str | None, text: str) -> str | None:
    if raw is not None:
        match = _DURATION.search(raw)
        if match is not None:
            return _duration_from_match(match)
        return _clean(raw, 80)

    match = re.search(
        r"(?i)(?:downtime|down time|stopped|offline|down)\D{0,24}?"
        r"(\d+(?:\.\d+)?)\s*"
        r"(minutes?|mins?|min|m|hours?|hrs?|hr|h|days?|d|shifts?)\b",
        text,
    )
    if match is not None:
        return _duration_from_match(match)

    match = re.search(
        r"(?i)(\d+(?:\.\d+)?)\s*"
        r"(minutes?|mins?|min|m|hours?|hrs?|hr|h|days?|d|shifts?)"
        r"\s*(?:of\s+)?(?:downtime|down time)\b",
        text,
    )
    if match is not None:
        return _duration_from_match(match)
    return None


def _severity(raw: str | None, text: str) -> FaultSeverity | None:
    if raw is not None:
        token = re.split(r"[^a-z]+", raw.lower().strip())[0]
        aliases = {
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
        mapped = aliases.get(token)
        if mapped is not None:
            return mapped

    lowered = text.lower()
    if any(signal in lowered for signal in _CRITICAL_SIGNALS):
        return "critical"
    if any(signal in lowered for signal in _HIGH_SIGNALS):
        return "high"
    if any(signal in lowered for signal in _MEDIUM_SIGNALS):
        return "medium"
    if any(signal in lowered for signal in _LOW_SIGNALS):
        return "low"
    return None


def extract_fault_summary(report: str) -> FaultSummary:
    """Extract structured fields from a maintenance report without AI."""

    text = report.strip()
    labels = _parse_labels(text)

    machine = _clean(
        _find_labeled(labels, text, ("machine", "equipment", "asset", "unit", "line")),
        120,
    )
    if machine is None:
        match = _EQUIPMENT.search(text)
        if match is not None:
            equipment = match.group(1)
            if equipment.islower():
                equipment = equipment.capitalize()
            machine = _clean(f"{equipment} {match.group(2)}", 120)

    fault_description = _clean(
        _find_labeled(
            labels,
            text,
            (
                "fault description",
                "fault",
                "failure",
                "issue",
                "problem",
                "symptom",
                "description",
            ),
        ),
        500,
    )
    if fault_description is None:
        fault_description = _first_sentence_with(text, _FAULT_KEYWORDS, 500)

    temperature, unit = _temperature(
        _find_labeled(labels, text, ("temperature", "temp", "operating temperature")),
        text,
    )

    downtime = _downtime(
        _find_labeled(
            labels,
            text,
            (
                "downtime",
                "down time",
                "downtime duration",
                "production downtime",
                "offline duration",
            ),
        ),
        text,
    )

    action_taken = _clean(
        _find_labeled(
            labels,
            text,
            (
                "action taken",
                "corrective action",
                "maintenance action",
                "action",
                "resolution",
                "resolved by",
                "repair",
                "fix",
            ),
        ),
        500,
    )
    if action_taken is None:
        action_taken = _first_sentence_with(text, _ACTION_KEYWORDS, 500)

    severity = _severity(
        _find_labeled(labels, text, ("severity", "priority", "risk level", "risk")),
        text,
    )

    return FaultSummary(
        machine=machine,
        fault_description=fault_description,
        temperature=temperature,
        temperature_unit=unit if temperature is not None else None,
        downtime=downtime,
        action_taken=action_taken,
        severity=severity,
    )
