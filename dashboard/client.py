"""HTTP client for the AI Adapter admin API used by the dashboard."""

from __future__ import annotations

import re
from typing import cast

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from dashboard import __version__
from dashboard.config import DashboardConfigurationError, DashboardSettings
from dashboard.metrics import MAX_METRICS_CHARS
from dashboard.models import (
    HealthStatus,
    ModelVersionList,
    MonitoringReport,
    ProviderHealthReport,
    ProviderSummary,
    ReadinessStatus,
    RequestLogPage,
)

_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_WINDOWS = frozenset({"15m", "1h", "6h", "24h", "7d", "30d"})
_KINDS = frozenset({"generation", "fault_report"})
_STATUSES = frozenset({"success", "degraded", "error"})


class DashboardApiError(Exception):
    """A safe, displayable API failure with no credentials or raw payloads."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


def _safe_message(value: str) -> str:
    text = " ".join(_CONTROL.sub(" ", value).split())
    return text[:300] or "The AI Adapter API returned an error."


def _response_error(response: httpx.Response) -> DashboardApiError:
    code = "http_error"
    message = f"AI Adapter API returned HTTP {response.status_code}."
    retryable = response.status_code in _RETRYABLE_STATUS
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            candidate_code = error.get("code")
            if isinstance(candidate_code, str) and _CODE.fullmatch(candidate_code):
                code = candidate_code
            candidate_message = error.get("message")
            if isinstance(candidate_message, str) and candidate_message.strip():
                message = _safe_message(candidate_message)
            retryable = bool(error.get("retryable", retryable))
    return DashboardApiError(
        code,
        message,
        status_code=response.status_code,
        retryable=retryable,
    )


def _invalid_response() -> DashboardApiError:
    return DashboardApiError(
        "invalid_response",
        "The AI Adapter API returned an unexpected response.",
    )


def _model[ModelT: BaseModel](model_type: type[ModelT], payload: object) -> ModelT:
    try:
        return model_type.model_validate(payload)
    except ValidationError:
        raise _invalid_response() from None


def _invalid_filter(message: str) -> DashboardApiError:
    return DashboardApiError("invalid_request", message)


class ApiClient:
    """Small read-only client with explicit redirect and error handling."""

    def __init__(
        self,
        settings: DashboardSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            trust_env=settings.trust_env,
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": f"ai-adapter-dashboard/{__version__}"},
        )

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _headers(self, *, auth: bool, text: bool) -> dict[str, str]:
        headers = {"Accept": "text/plain" if text else "application/json"}
        key = self._settings.admin_api_key
        if auth and key is not None:
            headers["Authorization"] = f"Bearer {key.get_secret_value()}"
        return headers

    def _get(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
        accept: tuple[int, ...] = (200,),
        auth: bool = True,
        text: bool = False,
        use_prefix: bool = True,
    ) -> object:
        try:
            url = (
                self._settings.api_url(path)
                if use_prefix
                else self._settings.origin_url(path)
            )
        except DashboardConfigurationError:
            raise _invalid_filter("The dashboard API path is invalid.") from None
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._headers(auth=auth, text=text),
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "api_timeout",
                "The AI Adapter API did not respond within "
                f"{self._settings.request_timeout_seconds:g} seconds.",
                retryable=True,
            ) from None
        except httpx.HTTPError:
            raise DashboardApiError(
                "api_unreachable",
                "Could not reach the AI Adapter API. Check the base URL and "
                "that the service is running.",
                retryable=True,
            ) from None
        if response.status_code not in accept:
            raise _response_error(response)
        if text:
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            if content_type != "text/plain":
                raise _invalid_response()
            body = response.text
            if len(body) > MAX_METRICS_CHARS:
                raise DashboardApiError(
                    "invalid_response",
                    "The metrics response exceeded the dashboard size limit.",
                )
            return body
        try:
            return response.json()
        except ValueError:
            raise _invalid_response() from None

    def live(self) -> HealthStatus:
        return _model(
            HealthStatus,
            self._get("/health/live", auth=False, use_prefix=False),
        )

    def readiness(self) -> ReadinessStatus:
        return _model(
            ReadinessStatus,
            self._get(
                "/health/ready",
                accept=(200, 503),
                auth=False,
                use_prefix=False,
            ),
        )

    def providers(self) -> list[ProviderSummary]:
        payload = self._get("/providers")
        try:
            return TypeAdapter(list[ProviderSummary]).validate_python(payload)
        except ValidationError:
            raise _invalid_response() from None

    def provider_health(self, provider: str) -> ProviderHealthReport:
        if not _PROVIDER.fullmatch(provider):
            raise _invalid_filter("The provider name is invalid.")
        return _model(
            ProviderHealthReport,
            self._get(f"/providers/{provider}/health"),
        )

    def model_versions(self) -> ModelVersionList:
        return _model(ModelVersionList, self._get("/model-versions"))

    def monitoring_summary(
        self,
        *,
        window: str,
        kind: str | None = None,
        provider: str | None = None,
    ) -> MonitoringReport:
        if window not in _WINDOWS:
            raise _invalid_filter("The monitoring window is invalid.")
        if kind is not None and kind not in _KINDS:
            raise _invalid_filter("The request kind filter is invalid.")
        if provider is not None and not _PROVIDER.fullmatch(provider):
            raise _invalid_filter("The provider filter is invalid.")
        params: dict[str, object] = {"window": window}
        if kind is not None:
            params["kind"] = kind
        if provider is not None:
            params["provider"] = provider
        return _model(
            MonitoringReport,
            self._get("/monitoring/summary", params=params),
        )

    def prometheus_metrics(self) -> str:
        return cast(str, self._get("/monitoring/metrics", text=True))

    def requests(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        provider: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> RequestLogPage:
        if kind is not None and kind not in _KINDS:
            raise _invalid_filter("The request kind filter is invalid.")
        if status is not None and status not in _STATUSES:
            raise _invalid_filter("The request status filter is invalid.")
        if provider is not None and not _PROVIDER.fullmatch(provider):
            raise _invalid_filter("The provider filter is invalid.")
        if not 1 <= limit <= 200 or offset < 0:
            raise _invalid_filter("The request paging filter is invalid.")
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if kind is not None:
            params["kind"] = kind
        if status is not None:
            params["status"] = status
        if provider is not None:
            params["provider"] = provider
        return _model(RequestLogPage, self._get("/requests", params=params))
