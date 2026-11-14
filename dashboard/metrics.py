"""Bounded parsing and summarization of Prometheus text exposition."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

MAX_METRICS_CHARS = 2_000_000
_MAX_LINE_LENGTH = 4096
_MAX_LABELS = 32
_MAX_LABEL_VALUE = 256
_NAME = re.compile(r"^[A-Za-z_:][A-Za-z0-9_:]*$")
_LABEL = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    labels: Mapping[str, str]
    value: float


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    requests_by_status: Mapping[str, int]
    total_requests: int
    accepted: int
    errors: int
    provider_failures: int
    fallbacks: int
    retries: int
    cost_usd: float
    tokens_by_type: Mapping[str, float]

    @property
    def total_tokens(self) -> float:
        if "total" in self.tokens_by_type:
            return self.tokens_by_type["total"]
        return self.tokens_by_type.get("prompt", 0.0) + self.tokens_by_type.get(
            "completion", 0.0
        )


def _unescape(value: str) -> str:
    result: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            result.append({"n": "\n", "\\": "\\", '"': '"'}.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    return "".join(result)


def _label_block(line: str, start: int) -> tuple[dict[str, str], str] | None:
    in_quotes = False
    escaped = False
    for index in range(start + 1, len(line)):
        char = line[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_quotes:
            escaped = True
            continue
        if char == '"':
            in_quotes = not in_quotes
            continue
        if char == "}" and not in_quotes:
            raw = line[start + 1 : index]
            labels: dict[str, str] = {}
            for match in _LABEL.finditer(raw):
                if len(labels) >= _MAX_LABELS:
                    return None
                key, value = match.group(1), _unescape(match.group(2))
                if len(value) > _MAX_LABEL_VALUE:
                    return None
                labels[key] = value
            return labels, line[index + 1 :]
    return None


def _parse_line(line: str) -> MetricSample | None:
    if "{" in line:
        brace = line.find("{")
        name = line[:brace].strip()
        block = _label_block(line, brace)
        if block is None:
            return None
        labels, remainder = block
    else:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            return None
        name, remainder = parts[0], parts[1]
        labels = {}
    if not _NAME.fullmatch(name):
        return None
    tokens = remainder.split()
    if not tokens:
        return None
    try:
        value = float(tokens[0])
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return MetricSample(name=name, labels=labels, value=value)


def parse_metrics(text: str) -> tuple[MetricSample, ...]:
    """Parse exposition text, skipping malformed and oversized lines."""

    if len(text) > MAX_METRICS_CHARS:
        raise ValueError("metrics exposition exceeds the dashboard size limit")
    samples: list[MetricSample] = []
    for raw in text.splitlines():
        if len(raw) > _MAX_LINE_LENGTH:
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sample = _parse_line(line)
        if sample is not None:
            samples.append(sample)
    return tuple(samples)


def _sum(
    samples: tuple[MetricSample, ...],
    name: str,
    *,
    labels: Mapping[str, str] | None = None,
) -> float:
    total = 0.0
    for sample in samples:
        if sample.name != name:
            continue
        if labels and any(
            sample.labels.get(key) != value for key, value in labels.items()
        ):
            continue
        total += sample.value
    return total


def _count(value: float) -> int:
    return max(int(round(value)), 0)


def summarize_metrics(samples: tuple[MetricSample, ...]) -> MetricsSnapshot:
    requests_by_status: dict[str, int] = {}
    for sample in samples:
        if sample.name != "ai_adapter_requests_total":
            continue
        status = sample.labels.get("status", "unknown")[:32]
        requests_by_status[status] = requests_by_status.get(status, 0) + _count(
            sample.value
        )
    tokens: dict[str, float] = {}
    for sample in samples:
        if sample.name != "ai_adapter_tokens_total":
            continue
        token_type = sample.labels.get("token_type", "unspecified")[:32]
        tokens[token_type] = tokens.get(token_type, 0.0) + max(sample.value, 0.0)
    return MetricsSnapshot(
        requests_by_status=requests_by_status,
        total_requests=sum(requests_by_status.values()),
        accepted=_count(_sum(samples, "ai_adapter_accepted_results_total")),
        errors=_count(_sum(samples, "ai_adapter_errors_total")),
        provider_failures=_count(
            _sum(samples, "ai_adapter_provider_failures_total")
        ),
        fallbacks=_count(_sum(samples, "ai_adapter_fallbacks_total")),
        retries=_count(_sum(samples, "ai_adapter_retries_total")),
        cost_usd=max(_sum(samples, "ai_adapter_cost_usd_total"), 0.0),
        tokens_by_type=tokens,
    )


def _is_counter_row(name: str) -> bool:
    return not name.endswith(("_created", "_bucket", "_sum", "_count"))


def counter_rows(samples: tuple[MetricSample, ...]) -> list[dict[str, object]]:
    """Return displayable counter rows without histogram internals."""

    rows: list[dict[str, object]] = []
    for sample in samples:
        if not _is_counter_row(sample.name):
            continue
        labels = ", ".join(
            f"{key}={value}" for key, value in sorted(sample.labels.items())
        )[:240]
        value: object = (
            int(sample.value)
            if float(sample.value).is_integer()
            else round(sample.value, 6)
        )
        rows.append(
            {"Metric": sample.name, "Labels": labels, "Value": value}
        )
    rows.sort(key=lambda row: (str(row["Metric"]), str(row["Labels"])))
    return rows
