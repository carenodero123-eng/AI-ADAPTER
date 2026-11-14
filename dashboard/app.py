"""Streamlit monitoring dashboard for the AI Adapter admin API."""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

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
from dashboard.metrics import counter_rows, parse_metrics, summarize_metrics
from dashboard.models import (
    KindPerformanceSummary,
    MonitoringReport,
    ProviderPerformanceSummary,
)

WINDOWS = ("15m", "1h", "6h", "24h", "7d", "30d")
VIEWS = (
    "Overview",
    "Providers",
    "Requests",
    "Model versions",
    "Prometheus metrics",
)
KIND_OPTIONS = ("All kinds", "generation", "fault_report")
STATUS_OPTIONS = ("All statuses", "success", "degraded", "error")
RAW_METRICS_DISPLAY_LIMIT = 200_000


def _render_api_error(error: DashboardApiError) -> None:
    if error.code == "authentication_required":
        st.error(
            "The API requires an admin key. Enter one in the sidebar "
            "or set DASHBOARD_ADMIN_API_KEY."
        )
    elif error.code == "permission_denied":
        st.error("The provided API key does not have administrator access.")
    elif error.code == "rate_limit_exceeded":
        st.warning("The API rate limit was exceeded. Wait, then refresh.")
    elif error.code == "monitoring_unavailable":
        st.warning(
            "Durable cost and latency monitoring is unavailable. Enable "
            "DATABASE_ENABLED, apply migrations, and confirm readiness."
        )
    elif error.code == "persistence_unavailable":
        st.warning(
            "Request history is unavailable. Check the database and readiness."
        )
    elif error.code == "model_catalog_unavailable":
        st.info(
            "The model-version catalog is disabled. Set "
            "MODEL_VERSION_MANIFEST to enable it."
        )
    else:
        st.error(error.message)
        if error.retryable:
            st.caption("This error may be temporary; use Refresh to retry.")


def _provider_names(client: ApiClient) -> list[str]:
    try:
        return [provider.name for provider in client.providers()]
    except DashboardApiError:
        return []


def _metric_row(entries: list[tuple[str, str]]) -> None:
    columns = st.columns(len(entries))
    for column, (label, value) in zip(columns, entries, strict=True):
        column.metric(label, value)


def _kind_rows(kinds: list[KindPerformanceSummary]) -> list[dict[str, str]]:
    return [
        {
            "Kind": item.kind,
            "Requests": format_count(item.requests),
            "Accepted": format_count(item.accepted),
            "Errors": format_count(item.errors),
            "p50 latency": format_ms(item.latency.p50_ms),
            "p95 latency": format_ms(item.latency.p95_ms),
            "Cost (USD)": format_usd(item.cost_usd),
            "Cost / accepted (USD)": format_usd(
                item.cost_per_accepted_result_usd
            ),
        }
        for item in kinds
    ]


def _provider_rows(
    providers: list[ProviderPerformanceSummary],
) -> list[dict[str, str]]:
    return [
        {
            "Provider": item.provider,
            "Requests": format_count(item.requests),
            "Accepted": format_count(item.accepted),
            "Provider failures": format_count(item.provider_failures),
            "Fallbacks": format_count(item.fallback_requests),
            "p50 latency": format_ms(item.latency.p50_ms),
            "p95 latency": format_ms(item.latency.p95_ms),
            "Cost (USD)": format_usd(item.cost_usd),
            "Cost / accepted (USD)": format_usd(
                item.cost_per_accepted_result_usd
            ),
        }
        for item in providers
    ]


def _render_overview(client: ApiClient) -> None:
    provider_options = ["All providers", *_provider_names(client)]
    columns = st.columns(3)
    window = columns[0].selectbox(
        "Window", WINDOWS, index=3, key="overview_window"
    )
    kind_label = columns[1].selectbox(
        "Request kind", KIND_OPTIONS, key="overview_kind"
    )
    provider_label = columns[2].selectbox(
        "Provider", provider_options, key="overview_provider"
    )
    kind = None if kind_label == KIND_OPTIONS[0] else kind_label
    provider = None if provider_label == provider_options[0] else provider_label

    try:
        report = client.monitoring_summary(
            window=window, kind=kind, provider=provider
        )
    except DashboardApiError as error:
        _render_api_error(error)
        return

    _render_summary(report)


def _render_summary(report: MonitoringReport) -> None:
    totals = report.totals
    _metric_row(
        [
            ("Requests", format_count(totals.requests)),
            ("Accepted rate", format_percent(totals.accepted_rate)),
            ("p50 latency", format_ms(totals.latency.p50_ms)),
            ("p95 latency", format_ms(totals.latency.p95_ms)),
        ]
    )
    _metric_row(
        [
            ("Cost / request", format_usd(totals.cost_per_request_usd)),
            (
                "Cost / accepted result",
                format_usd(totals.cost_per_accepted_result_usd),
            ),
            (
                "Provider failure rate",
                format_percent(totals.provider_failure_rate),
            ),
            ("Fallback rate", format_percent(totals.fallback_rate)),
        ]
    )
    st.caption(
        f"Window {format_utc(report.window_start)} to "
        f"{format_utc(report.window_end)}. Latency sample: "
        f"{format_count(totals.latency.sample_size)} durations"
        + (
            " (truncated to the newest sample)."
            if totals.latency.sample_truncated
            else "."
        )
    )
    if totals.requests == 0:
        st.info("No requests were recorded in this window.")
        return

    providers = [item for item in report.by_provider if item.requests > 0]
    latency_rows = [
        {
            "Provider": item.provider,
            "p50 (ms)": item.latency.p50_ms,
            "p95 (ms)": item.latency.p95_ms,
        }
        for item in providers
        if item.latency.p50_ms is not None and item.latency.p95_ms is not None
    ]
    if latency_rows:
        st.subheader("Latency by provider")
        st.bar_chart(
            latency_rows,
            x="Provider",
            y=["p50 (ms)", "p95 (ms)"],
            width="stretch",
        )

    if providers:
        st.subheader("Outcomes by provider")
        st.bar_chart(
            [
                {
                    "Provider": item.provider,
                    "Accepted": item.accepted,
                    "Errors": item.errors,
                    "Fallbacks": item.fallback_requests,
                }
                for item in providers
            ],
            x="Provider",
            y=["Accepted", "Errors", "Fallbacks"],
            width="stretch",
        )
        st.subheader("Cost by provider")
        st.bar_chart(
            [
                {"Provider": item.provider, "Cost (USD)": item.cost_usd}
                for item in providers
            ],
            x="Provider",
            y="Cost (USD)",
            width="stretch",
        )

    if report.by_kind:
        st.subheader("By request kind")
        st.dataframe(
            _kind_rows(report.by_kind), width="stretch", hide_index=True
        )
    if report.by_provider:
        st.subheader("By provider")
        st.dataframe(
            _provider_rows(report.by_provider),
            width="stretch",
            hide_index=True,
        )


def _render_providers(client: ApiClient) -> None:
    try:
        providers = client.providers()
    except DashboardApiError as error:
        _render_api_error(error)
        return
    if not providers:
        st.info("No providers are registered.")
        return
    st.dataframe(
        [
            {
                "Provider": item.name,
                "Display name": item.display_name,
                "Kind": item.kind,
                "Default": "yes" if item.is_default else "no",
                "Default model": item.default_model,
                "Models": ", ".join(item.models),
            }
            for item in providers
        ],
        width="stretch",
        hide_index=True,
    )
    columns = st.columns([2, 1])
    selected = columns[0].selectbox(
        "Provider health",
        [item.name for item in providers],
        key="health_provider",
    )
    clicked = columns[1].button(
        "Check health", key="check_health", width="stretch"
    )
    if not clicked:
        st.caption(
            "Health checks call the provider and are only run when requested."
        )
        return
    try:
        health = client.provider_health(selected)
    except DashboardApiError as error:
        _render_api_error(error)
        return
    _metric_row(
        [
            ("Provider status", health.status),
            ("Health latency", format_ms(health.latency_ms)),
            (
                "Circuit",
                health.circuit.state if health.circuit is not None else "n/a",
            ),
        ]
    )
    if health.circuit is not None:
        st.caption(
            f"Circuit failures: {format_count(health.circuit.failure_count)}."
        )
    if health.detail:
        st.text(health.detail)


def _render_requests(client: ApiClient) -> None:
    columns = st.columns(4)
    kind_label = columns[0].selectbox(
        "Request kind", KIND_OPTIONS, key="requests_kind"
    )
    status_label = columns[1].selectbox(
        "Status", STATUS_OPTIONS, key="requests_status"
    )
    limit = columns[2].selectbox(
        "Page size", (25, 50, 100, 200), index=1, key="requests_limit"
    )
    offset = columns[3].number_input(
        "Offset",
        min_value=0,
        max_value=1_000_000,
        value=0,
        step=25,
        key="requests_offset",
    )
    try:
        page = client.requests(
            kind=None if kind_label == KIND_OPTIONS[0] else kind_label,
            status=(
                None if status_label == STATUS_OPTIONS[0] else status_label
            ),
            limit=limit,
            offset=offset,
        )
    except DashboardApiError as error:
        _render_api_error(error)
        return
    if page.total == 0:
        st.info("No request records match these filters.")
        return
    if not page.items:
        st.info("No records exist at this offset.")
        return
    st.caption(
        f"Showing {page.offset + 1} to {page.offset + len(page.items)} of "
        f"{format_count(page.total)} records. Prompts and completions are "
        "never stored, so they cannot appear here."
    )
    st.dataframe(
        [
            {
                "Occurred (UTC)": format_utc(item.occurred_at),
                "Record": item.id,
                "Request ID": item.request_id,
                "Kind": item.kind,
                "Status": item.status,
                "Provider": item.provider or "",
                "Model": item.model or "",
                "Duration": format_ms(item.duration_ms),
                "Tokens": format_count(item.total_tokens),
                "Cost (USD)": format_usd(item.cost_usd),
                "Retries": item.retry_count,
                "Fallback": (
                    f"yes ({item.fallback_reason})"
                    if item.fallback_used and item.fallback_reason
                    else ("yes" if item.fallback_used else "no")
                ),
                "HTTP": item.http_status,
                "Error": item.error_code or "",
            }
            for item in page.items
        ],
        width="stretch",
        hide_index=True,
    )


def _render_models(client: ApiClient) -> None:
    try:
        catalog = client.model_versions()
    except DashboardApiError as error:
        _render_api_error(error)
        return
    if not catalog.models:
        st.info("The model-version catalog is empty.")
        return
    active = sum(1 for item in catalog.models if item.status == "active")
    st.caption(
        f"{format_count(len(catalog.models))} tracked model releases; "
        f"{format_count(active)} active."
    )
    st.dataframe(
        [
            {
                "Provider": item.provider,
                "Model": item.model,
                "Version": item.version,
                "Status": item.status,
                "Released": item.released_on or "",
                "Configured": "yes" if item.configured else "no",
                "Notes": item.notes or "",
            }
            for item in catalog.models
        ],
        width="stretch",
        hide_index=True,
    )


def _render_metrics(client: ApiClient) -> None:
    try:
        text = client.prometheus_metrics()
    except DashboardApiError as error:
        _render_api_error(error)
        return
    try:
        samples = parse_metrics(text)
    except ValueError:
        st.error(
            "The metrics response exceeded the dashboard size limit and was "
            "not rendered."
        )
        return
    snapshot = summarize_metrics(samples)
    st.caption(
        "Process-local counters observed since the API process started. They "
        "reset on restart. Use Overview for durable, cross-restart totals."
    )
    _metric_row(
        [
            ("Process requests", format_count(snapshot.total_requests)),
            ("Accepted results", format_count(snapshot.accepted)),
            ("Errors", format_count(snapshot.errors)),
            ("Provider failures", format_count(snapshot.provider_failures)),
        ]
    )
    _metric_row(
        [
            ("Fallbacks", format_count(snapshot.fallbacks)),
            ("Retries", format_count(snapshot.retries)),
            ("Process cost", format_usd(snapshot.cost_usd)),
            (
                "Tokens",
                format_count(int(round(snapshot.total_tokens))),
            ),
        ]
    )
    if snapshot.requests_by_status:
        breakdown = ", ".join(
            f"{status}: {format_count(count)}"
            for status, count in sorted(snapshot.requests_by_status.items())
        )
        st.caption(f"Requests by status: {breakdown}.")
    rows = counter_rows(samples)
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No counter series are available yet.")
    with st.expander("Raw Prometheus exposition"):
        if len(text) > RAW_METRICS_DISPLAY_LIMIT:
            st.code(
                text[:RAW_METRICS_DISPLAY_LIMIT],
                language="text",
                wrap_lines=True,
            )
            st.caption("Raw text was truncated for display.")
        else:
            st.code(text, language="text", wrap_lines=True)


def _configure_sidebar() -> tuple[DashboardSettings, str]:
    try:
        environment_settings = load_dashboard_settings()
    except DashboardConfigurationError as error:
        st.sidebar.error(str(error))
        st.stop()
    with st.sidebar:
        st.header("Connection")
        base_url = st.text_input(
            "API base URL",
            value=environment_settings.api_base_url,
            key="api_base_url",
        )
        key_input: str | None = None
        if environment_settings.admin_api_key is not None:
            st.caption("Admin key loaded from DASHBOARD_ADMIN_API_KEY.")
        else:
            key_input = st.text_input(
                "Admin API key",
                type="password",
                key="admin_key",
                help=(
                    "Held in this browser session only. It is never written "
                    "to disk, URLs, or logs."
                ),
            )
        try:
            settings = (
                environment_settings
                if environment_settings.admin_api_key is not None
                else environment_settings.with_admin_key(key_input)
            )
            settings = replace(settings, api_base_url=base_url)
        except DashboardConfigurationError as error:
            st.error(str(error))
            st.stop()
        if settings.is_remote_plain_http:
            st.warning(
                "This remote API uses plain HTTP. The admin key would cross "
                "the network unencrypted; use HTTPS or a local tunnel."
            )
        if st.button(
            "Refresh", key="refresh_dashboard", width="stretch"
        ):
            st.rerun()
        st.divider()
        view = st.radio("View", VIEWS, key="dashboard_view")
    return settings, view


def main() -> None:
    st.set_page_config(
        page_title="AI Adapter Monitoring",
        layout="wide",
    )
    st.title("AI Adapter Monitoring")
    st.caption(
        "Read-only operational view of the AI Adapter admin API. Prompts, "
        "report text, API keys, and credentials are never displayed."
    )
    settings, view = _configure_sidebar()

    client = ApiClient(settings)
    try:
        live = client.live()
        ready = client.readiness()
    except DashboardApiError as error:
        client.close()
        st.error("Cannot reach the AI Adapter API.")
        st.caption(error.message)
        st.caption(f"Configured base URL: {settings.api_base_url}")
        st.info("Start the API, then confirm the base URL and admin key.")
        st.code(".\\scripts\\run-dev.ps1", language="powershell")
        st.stop()

    st.caption(
        f"{live.service} {live.version} | {live.environment} | "
        f"API {ready.status}"
    )
    if ready.status != "ready":
        checks = ", ".join(
            f"{name}: {state}" for name, state in sorted(ready.checks.items())
        )
        st.warning(f"The API is not ready ({checks}).")

    try:
        if view == "Overview":
            _render_overview(client)
        elif view == "Providers":
            _render_providers(client)
        elif view == "Requests":
            _render_requests(client)
        elif view == "Model versions":
            _render_models(client)
        else:
            _render_metrics(client)
    finally:
        client.close()


main()
