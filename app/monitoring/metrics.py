"""Process-local Prometheus metrics for every completed AI request."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from app.database.records import RequestLogEntry

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

_LATENCY_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)


def _label(value: str | None, fallback: str) -> str:
    normalized = (value or "").strip()
    return normalized[:64] if normalized else fallback


class MetricsCollector:
    """Use bounded labels only; prompts, keys, and request IDs are excluded."""

    def __init__(self) -> None:
        self._registry = CollectorRegistry(auto_describe=True)
        self._requests = Counter(
            "ai_adapter_requests",
            "Completed AI requests by kind, provider, and status.",
            ("kind", "provider", "status"),
            registry=self._registry,
        )
        self._latency = Histogram(
            "ai_adapter_request_duration_seconds",
            "End-to-end AI request duration in seconds.",
            ("kind", "provider"),
            buckets=_LATENCY_BUCKETS,
            registry=self._registry,
        )
        self._cost = Counter(
            "ai_adapter_cost_usd",
            "Estimated provider cost in USD.",
            ("kind", "provider"),
            registry=self._registry,
        )
        self._tokens = Counter(
            "ai_adapter_tokens",
            "Provider token usage.",
            ("kind", "provider", "token_type"),
            registry=self._registry,
        )
        self._retries = Counter(
            "ai_adapter_retries",
            "Provider attempts beyond the first attempt.",
            ("kind", "provider"),
            registry=self._registry,
        )
        self._fallbacks = Counter(
            "ai_adapter_fallbacks",
            "Requests that activated provider fallback.",
            ("kind", "reason"),
            registry=self._registry,
        )
        self._accepted = Counter(
            "ai_adapter_accepted_results",
            "Responses accepted after output validation.",
            ("kind",),
            registry=self._registry,
        )
        self._errors = Counter(
            "ai_adapter_errors",
            "Failed requests by safe application error code.",
            ("kind", "error_code"),
            registry=self._registry,
        )
        self._provider_failures = Counter(
            "ai_adapter_provider_failures",
            "Failed requests attributed to a provider.",
            ("provider", "error_code"),
            registry=self._registry,
        )

    def observe(self, entry: RequestLogEntry) -> None:
        provider = _label(entry.provider, "none")
        if entry.error_code == "provider_not_found":
            # Client-supplied names must not create unbounded label values.
            provider = "unconfigured"
        kind = entry.kind
        status = entry.status
        error_code = _label(entry.error_code, "unknown")

        self._requests.labels(kind, provider, status).inc()
        if entry.duration_ms >= 0:
            self._latency.labels(kind, provider).observe(entry.duration_ms / 1000)
        cost = max(float(entry.cost_usd), 0.0)
        if cost:
            self._cost.labels(kind, provider).inc(cost)
        for token_type, amount in (
            ("prompt", entry.prompt_tokens),
            ("completion", entry.completion_tokens),
            ("total", entry.total_tokens),
        ):
            if amount > 0:
                self._tokens.labels(kind, provider, token_type).inc(amount)
        if entry.retry_count > 0:
            self._retries.labels(kind, provider).inc(entry.retry_count)
        if entry.fallback_used:
            self._fallbacks.labels(
                kind, _label(entry.fallback_reason, "unspecified")
            ).inc()
        if status in ("success", "degraded"):
            self._accepted.labels(kind).inc()
        else:
            self._errors.labels(kind, error_code).inc()
            if entry.provider is not None:
                self._provider_failures.labels(provider, error_code).inc()

    def render(self) -> bytes:
        return generate_latest(self._registry)
