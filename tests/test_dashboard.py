"""Stage L dashboard configuration, client, parsing, and UI tests."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from app.core.config import Settings
from app.main import create_app
from dashboard.client import ApiClient, DashboardApiError
from dashboard.config import (
    DashboardConfigurationError,
    DashboardSettings,
    load_dashboard_settings,
)
from dashboard.formatting import (
    format_count,
    format_ms,
    format_percent,
    format_usd,
    format_utc,
)
from dashboard.metrics import (
    MAX_METRICS_CHARS,
    counter_rows,
    parse_metrics,
    summarize_metrics,
)
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
ADMIN_KEY = "admin-key-0123456789abcdef"
USER_KEY = "user-key-0123456789abcdef"


def _settings(**overrides: object) -> DashboardSettings:
    values: dict[str, object] = {
        "api_base_url": "http://127.0.0.1:8000",
        "admin_api_key": SecretStr(ADMIN_KEY),
    }
    values.update(overrides)
    return DashboardSettings(**values)


def _latency(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "average_ms": 12.0,
        "p50_ms": 10.0,
        "p95_ms": 20.0,
        "min_ms": 5.0,
        "max_ms": 25.0,
        "sample_size": 4,
        "sample_truncated": False,
    }
    values.update(overrides)
    return values


def _performance(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "requests": 4,
        "accepted": 3,
        "successful": 2,
        "degraded": 1,
        "errors": 1,
        "accepted_rate": 0.75,
        "success_rate": 0.5,
        "degraded_rate": 0.25,
        "error_rate": 0.25,
        "provider_requests": 4,
        "provider_failures": 1,
        "provider_failure_rate": 0.25,
        "fallback_requests": 1,
        "fallback_rate": 0.25,
        "retry_count": 2,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "cost_usd": 0.0001,
        "cost_per_request_usd": 0.000025,
        "cost_per_accepted_result_usd": 0.000033,
        "latency": _latency(),
    }
    values.update(overrides)
    return values


def _report_payload() -> dict[str, object]:
    return {
        "window": "1h",
        "window_start": "2026-11-14T11:00:00Z",
        "window_end": "2026-11-14T12:00:00Z",
        "generated_at": "2026-11-14T12:00:00Z",
        "latency_sample_limit": 10_000,
        "totals": _performance(),
        "by_kind": [{"kind": "generation", **_performance()}],
        "by_provider": [{"provider": "fake", **_performance()}],
    }


def _live_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "AI Adapter",
        "version": "0.1.0",
        "environment": "test",
        "uptime_seconds": 1.5,
    }


def _readiness_payload() -> dict[str, object]:
    return {"status": "ready", "checks": {"configuration": "ok"}}


def _provider_payload() -> list[dict[str, object]]:
    return [
        {
            "name": "fake",
            "display_name": "Fake provider",
            "kind": "local",
            "models": ["fake-small", "fake-large"],
            "default_model": "fake-small",
            "is_default": True,
        }
    ]


def _request_item() -> dict[str, object]:
    return {
        "id": 1,
        "request_id": "req-0000000000000001",
        "kind": "generation",
        "occurred_at": "2026-11-14T12:00:00Z",
        "auth_role": "admin",
        "selected_provider": "fake",
        "provider": "fake",
        "model": "fake-small",
        "duration_ms": 2.5,
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
        "cost_usd": 0.0,
        "retry_count": 0,
        "fallback_used": False,
        "fallback_reason": None,
        "providers_tried": ["fake"],
        "status": "success",
        "error_code": None,
        "http_status": 200,
        "extraction": None,
        "extraction_reason": None,
        "missing_field_count": None,
    }


def test_settings_normalize_and_redact_admin_key() -> None:
    settings = DashboardSettings(
        api_base_url="http://127.0.0.1:9000/",
        admin_api_key=SecretStr(ADMIN_KEY),
    )
    assert settings.api_base_url == "http://127.0.0.1:9000"
    assert (
        settings.api_url("/health/live")
        == "http://127.0.0.1:9000/api/v1/health/live"
    )
    assert settings.with_admin_key("  padded-key-0123456789  ").admin_api_key
    assert (
        settings.with_admin_key("  padded-key-0123456789  ")
        .admin_api_key.get_secret_value()
        == "padded-key-0123456789"
    )
    assert settings.with_admin_key("").admin_api_key is None
    assert settings.with_admin_key(None).admin_api_key is None
    assert ADMIN_KEY not in repr(settings)
    assert ADMIN_KEY not in str(settings)


@pytest.mark.parametrize(
    "base_url",
    (
        "ftp://127.0.0.1:8000",
        "http://user:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000/api",
        "http://127.0.0.1:8000?x=1",
        "http://127.0.0.1:8000#fragment",
        "http://127.0.0.1:0",
        "not-a-url",
    ),
)
def test_settings_reject_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(DashboardConfigurationError):
        DashboardSettings(api_base_url=base_url)


@pytest.mark.parametrize("prefix", ("api/v1", "/api/v1/", "/api/../v1"))
def test_settings_reject_invalid_prefix(prefix: str) -> None:
    with pytest.raises(DashboardConfigurationError):
        DashboardSettings(api_prefix=prefix)


@pytest.mark.parametrize(
    "key",
    ("short", "has whitespace inside 123456", "x" * 513),
)
def test_settings_reject_invalid_admin_keys(key: str) -> None:
    with pytest.raises(DashboardConfigurationError):
        _settings().with_admin_key(key)


def test_settings_flag_remote_plain_http() -> None:
    assert DashboardSettings(
        api_base_url="http://api.example.com"
    ).is_remote_plain_http
    assert not DashboardSettings(
        api_base_url="http://127.0.0.1:8000"
    ).is_remote_plain_http
    assert not DashboardSettings(
        api_base_url="https://api.example.com"
    ).is_remote_plain_http


def test_environment_loader_reads_bounded_values() -> None:
    settings = load_dashboard_settings(
        {
            "DASHBOARD_API_BASE_URL": "http://localhost:9000",
            "DASHBOARD_ADMIN_API_KEY": f"  {ADMIN_KEY}  ",
            "DASHBOARD_REQUEST_TIMEOUT_SECONDS": "5",
            "DASHBOARD_TRUST_ENV": "true",
        }
    )
    assert settings.api_base_url == "http://localhost:9000"
    assert settings.request_timeout_seconds == 5.0
    assert settings.trust_env is True
    assert settings.admin_api_key is not None
    assert settings.admin_api_key.get_secret_value() == ADMIN_KEY


def test_environment_loader_rejects_invalid_values() -> None:
    with pytest.raises(DashboardConfigurationError):
        load_dashboard_settings(
            {"DASHBOARD_REQUEST_TIMEOUT_SECONDS": "soon"}
        )
    with pytest.raises(DashboardConfigurationError):
        load_dashboard_settings({"DASHBOARD_TRUST_ENV": "maybe"})
    with pytest.raises(DashboardConfigurationError):
        load_dashboard_settings(
            {"DASHBOARD_REQUEST_TIMEOUT_SECONDS": "120"}
        )


def test_formatting_helpers() -> None:
    assert format_percent(0.666667) == "66.7%"
    assert format_percent(-1.0) == "0.0%"
    assert format_usd(0.0) == "$0.000000"
    assert format_usd(0.0001) == "$0.000100"
    assert format_usd(1234.5) == "$1,234.50"
    assert format_ms(None) == "n/a"
    assert format_ms(2.13) == "2.13 ms"
    assert format_ms(1234.5) == "1.23 s"
    assert format_count(1234) == "1,234"
    assert format_count(-5) == "0"
    assert format_utc(None) == "n/a"
    assert (
        format_utc(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
        == "2026-11-14 12:00:00 UTC"
    )


_METRICS_TEXT = """# HELP ai_adapter_requests_total Requests.
# TYPE ai_adapter_requests_total counter
ai_adapter_requests_total{kind="generation",provider="fake",status="success"} 2
ai_adapter_requests_total{kind="fault_report",provider="fake",status="degraded"} 1
ai_adapter_requests_total{kind="generation",provider="fake",status="error"} 1
ai_adapter_accepted_results_total{kind="generation"} 2
ai_adapter_errors_total{kind="generation",error_code="provider_timeout"} 1
ai_adapter_provider_failures_total{provider="fake",error_code="provider_timeout"} 1
ai_adapter_fallbacks_total{kind="generation",reason="provider_timeout"} 1
ai_adapter_retries_total 2
ai_adapter_cost_usd_total{kind="generation",provider="fake"} 0.0001
ai_adapter_tokens_total{kind="generation",provider="fake",token_type="prompt"} 10
ai_adapter_tokens_total{kind="generation",provider="fake",token_type="completion"} 5
ai_adapter_tokens_total{kind="generation",provider="fake",token_type="total"} 15
ai_adapter_request_duration_seconds_bucket{provider="fake",le="0.01"} 1
ai_adapter_request_duration_seconds_sum{provider="fake"} 0.5
ai_adapter_request_duration_seconds_count{provider="fake"} 2
custom_metric{a="quote\\"inside",b="line\\nbreak"} 3
not a metric line at all
"""


def test_metrics_parser_and_summary() -> None:
    samples = parse_metrics(_METRICS_TEXT)
    snapshot = summarize_metrics(samples)
    assert snapshot.requests_by_status == {
        "success": 2,
        "degraded": 1,
        "error": 1,
    }
    assert snapshot.total_requests == 4
    assert snapshot.accepted == 2
    assert snapshot.errors == 1
    assert snapshot.provider_failures == 1
    assert snapshot.fallbacks == 1
    assert snapshot.retries == 2
    assert snapshot.cost_usd == pytest.approx(0.0001)
    assert snapshot.tokens_by_type == {
        "prompt": 10.0,
        "completion": 5.0,
        "total": 15.0,
    }
    assert snapshot.total_tokens == 15.0

    escaped = next(item for item in samples if item.name == "custom_metric")
    assert escaped.labels["a"] == 'quote"inside'
    assert escaped.labels["b"] == "line\nbreak"

    names = {row["Metric"] for row in counter_rows(samples)}
    assert "ai_adapter_requests_total" in names
    assert "ai_adapter_request_duration_seconds_bucket" not in names
    assert "ai_adapter_request_duration_seconds_sum" not in names
    assert "ai_adapter_request_duration_seconds_count" not in names


def test_metrics_parser_is_bounded() -> None:
    with pytest.raises(ValueError):
        parse_metrics("x" * (MAX_METRICS_CHARS + 1))
    samples = parse_metrics("bad_metric invalid\n" + "y" * 5000 + " 1\n")
    assert samples == ()


def test_client_sends_summary_filters_and_admin_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_report_payload())

    with ApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        report = client.monitoring_summary(
            window="1h", kind="generation", provider="fake"
        )
    assert report.totals.requests == 4
    assert report.by_provider[0].provider == "fake"
    request = seen[0]
    assert request.url.path == "/api/v1/monitoring/summary"
    assert dict(request.url.params) == {
        "window": "1h",
        "kind": "generation",
        "provider": "fake",
    }
    assert request.headers["authorization"] == f"Bearer {ADMIN_KEY}"


def test_client_does_not_send_key_to_health_or_without_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/health/live"):
            return httpx.Response(200, json=_live_payload())
        if request.url.path.endswith("/health/ready"):
            return httpx.Response(200, json=_readiness_payload())
        return httpx.Response(200, json=_provider_payload())

    with ApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        assert client.live().status == "ok"
        assert client.readiness().status == "ready"
    assert all("authorization" not in request.headers for request in seen)

    settings = DashboardSettings(api_base_url="http://127.0.0.1:8000")
    with ApiClient(settings, transport=httpx.MockTransport(handler)) as client:
        assert client.providers()[0].name == "fake"
    assert all("authorization" not in request.headers for request in seen)


def test_client_maps_server_errors_without_payload_or_key_leakage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "permission_denied",
                    "message": "Administrator privileges are required.\n"
                    + "details " * 100,
                    "retryable": False,
                }
            },
        )

    with ApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.model_versions()
    error = captured.value
    assert error.code == "permission_denied"
    assert error.status_code == 403
    assert "\n" not in error.message
    assert len(error.message) <= 300
    assert ADMIN_KEY not in str(error)


def test_client_maps_non_json_and_redirect_failures() -> None:
    calls = 0

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            302, headers={"location": "https://example.invalid/steal"}
        )

    with ApiClient(
        _settings(), transport=httpx.MockTransport(redirect_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.providers()
    assert captured.value.code == "http_error"
    assert calls == 1

    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    with ApiClient(
        _settings(), transport=httpx.MockTransport(html_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.providers()
    assert captured.value.code == "http_error"
    assert "bad gateway" not in captured.value.message
    assert captured.value.retryable is True


def test_client_maps_timeouts_and_invalid_payloads() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out for {ADMIN_KEY}")

    with ApiClient(
        _settings(), transport=httpx.MockTransport(timeout_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.providers()
    assert captured.value.code == "api_timeout"
    assert ADMIN_KEY not in str(captured.value)

    def invalid_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with ApiClient(
        _settings(), transport=httpx.MockTransport(invalid_json_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.providers()
    assert captured.value.code == "invalid_response"

    def invalid_shape_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with ApiClient(
        _settings(), transport=httpx.MockTransport(invalid_shape_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.monitoring_summary(window="1h")
    assert captured.value.code == "invalid_response"


def test_client_metrics_content_type_and_size_limits() -> None:
    def text_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="ai_adapter_requests_total 1\n",
            headers={"content-type": "text/plain; version=0.0.4"},
        )

    with ApiClient(_settings(), transport=httpx.MockTransport(text_handler)) as client:
        assert "ai_adapter_requests_total" in client.prometheus_metrics()

    def wrong_type_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html></html>", headers={"content-type": "text/html"}
        )

    with ApiClient(
        _settings(), transport=httpx.MockTransport(wrong_type_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.prometheus_metrics()
    assert captured.value.code == "invalid_response"

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="x" * (MAX_METRICS_CHARS + 1),
            headers={"content-type": "text/plain"},
        )

    with ApiClient(
        _settings(), transport=httpx.MockTransport(oversized_handler)
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.prometheus_metrics()
    assert captured.value.code == "invalid_response"


def test_client_builds_history_filters_and_rejects_bad_inputs() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "items": [_request_item()],
                "total": 1,
                "limit": 50,
                "offset": 0,
            },
        )

    with ApiClient(_settings(), transport=httpx.MockTransport(handler)) as client:
        page = client.requests(
            kind="generation", status="success", provider="fake", limit=50
        )
        assert page.total == 1
        assert page.items[0].request_id == "req-0000000000000001"
        assert dict(seen[0].url.params) == {
            "kind": "generation",
            "status": "success",
            "provider": "fake",
            "limit": "50",
            "offset": "0",
        }
        for call in (
            lambda: client.provider_health("../etc"),
            lambda: client.monitoring_summary(window="2h"),
            lambda: client.monitoring_summary(window="1h", kind="other"),
            lambda: client.requests(limit=500),
        ):
            with pytest.raises(DashboardApiError) as captured:
                call()
            assert captured.value.code == "invalid_request"
    assert len(seen) == 1


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _api_settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        log_level="ERROR",
        log_format="console",
        database_enabled=True,
        database_url=SecretStr(
            f"sqlite+aiosqlite:///{database_path.as_posix()}"
        ),
        database_auto_create=True,
        security_require_auth=True,
        security_api_keys=SecretStr(USER_KEY),
        security_admin_api_keys=SecretStr(ADMIN_KEY),
        security_rate_limit_requests=1000,
        reliability_backoff_base_seconds=0.0,
        reliability_backoff_max_seconds=0.0,
        reliability_jitter_seconds=0.0,
        model_version_manifest=str(ROOT / "config" / "model_versions.json"),
    )


@pytest.fixture
def dashboard_api(tmp_path: Path) -> Iterator[str]:
    settings = _api_settings(tmp_path / "dashboard.db")
    app = create_app(settings)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("API server stopped during startup")
        if time.monotonic() > deadline:
            raise TimeoutError("API server did not start")
        time.sleep(0.05)
    base_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {ADMIN_KEY}"}
    try:
        with httpx.Client(
            base_url=base_url, trust_env=False, timeout=10.0
        ) as http:
            generation = http.post(
                "/api/v1/generate",
                headers=headers,
                json={
                    "model": "fake-small",
                    "messages": [
                        {"role": "user", "content": "dashboard smoke prompt"}
                    ],
                },
            )
            assert generation.status_code == 200
            fault = http.post(
                "/api/v1/fault-reports/summarize",
                headers=headers,
                json={
                    "report": (
                        "Pump P-101 reported high vibration for 5 minutes "
                        "at 80 C."
                    )
                },
            )
            assert fault.status_code == 200
        yield base_url
    finally:
        server.should_exit = True
        thread.join(10)


def test_dashboard_renders_every_view_against_live_api(
    dashboard_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DASHBOARD_API_BASE_URL", dashboard_api)
    monkeypatch.setenv("DASHBOARD_ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("DASHBOARD_REQUEST_TIMEOUT_SECONDS", "10")

    at = AppTest.from_file(
        str(ROOT / "dashboard" / "app.py"), default_timeout=60
    )
    at.run()
    assert not at.exception, str(at.exception)
    overview_metrics = {metric.label: metric.value for metric in at.metric}
    assert overview_metrics["Requests"] == "2"
    assert overview_metrics["Accepted rate"] == "100.0%"

    def open_view(name: str) -> None:
        radio = next(
            widget
            for widget in at.radio
            if widget.key == "dashboard_view"
        )
        radio.set_value(name)
        at.run()
        assert not at.exception, str(at.exception)

    open_view("Providers")
    assert at.dataframe
    check = next(
        widget for widget in at.button if widget.key == "check_health"
    )
    check.click()
    at.run()
    assert not at.exception, str(at.exception)
    health_metrics = {metric.label: metric.value for metric in at.metric}
    assert health_metrics["Provider status"] == "healthy"

    open_view("Requests")
    assert at.dataframe
    assert any("Showing 1 to 2" in caption.value for caption in at.caption)

    open_view("Model versions")
    assert at.dataframe

    open_view("Prometheus metrics")
    process_metrics = {metric.label: metric.value for metric in at.metric}
    assert process_metrics["Process requests"] == "2"
    assert process_metrics["Accepted results"] == "2"


def test_dashboard_client_enforces_admin_boundary(dashboard_api: str) -> None:
    with ApiClient(
        DashboardSettings(
            api_base_url=dashboard_api, admin_api_key=SecretStr(USER_KEY)
        )
    ) as client:
        with pytest.raises(DashboardApiError) as captured:
            client.monitoring_summary(window="1h")
    assert captured.value.code == "permission_denied"
    assert USER_KEY not in str(captured.value)
