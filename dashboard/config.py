"""Bounded dashboard configuration loaded from the environment."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from pydantic import SecretStr

_PREFIX = re.compile(r"^/[A-Za-z0-9._~/-]*$")
_PATH = re.compile(r"^/[A-Za-z0-9._~/-]*$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class DashboardConfigurationError(ValueError):
    """A dashboard setting is invalid; the message is safe to display."""


def _env_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise DashboardConfigurationError(f"{name} must be true or false.")


@dataclass(frozen=True, slots=True)
class DashboardSettings:
    """Connection settings for one dashboard process.

    The admin key is held in ``SecretStr`` so ordinary representations and logs
    never expose it. It is never written to disk by this package.
    """

    api_base_url: str = "http://127.0.0.1:8000"
    api_prefix: str = "/api/v1"
    admin_api_key: SecretStr | None = None
    request_timeout_seconds: float = 10.0
    trust_env: bool = False

    def __post_init__(self) -> None:
        raw = self.api_base_url.strip()
        parsed = urlparse(raw)
        try:
            port = parsed.port
        except ValueError:
            raise DashboardConfigurationError(
                "Dashboard API base URL contains an invalid port."
            ) from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or port == 0
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or any(char.isspace() for char in raw)
        ):
            raise DashboardConfigurationError(
                "Dashboard API base URL must be an http(s) origin without "
                "credentials, query, fragment, or path."
            )
        object.__setattr__(
            self, "api_base_url", f"{parsed.scheme}://{parsed.netloc}"
        )

        prefix = self.api_prefix.strip()
        if (
            not _PREFIX.fullmatch(prefix)
            or prefix.endswith("/")
            or ".." in prefix
        ):
            raise DashboardConfigurationError(
                "Dashboard API prefix must start with '/' and contain only "
                "URL path characters."
            )
        object.__setattr__(self, "api_prefix", prefix)

        timeout = float(self.request_timeout_seconds)
        if not 0.1 <= timeout <= 60.0:
            raise DashboardConfigurationError(
                "Dashboard request timeout must be between 0.1 and 60 seconds."
            )
        object.__setattr__(self, "request_timeout_seconds", timeout)

    @property
    def is_remote_plain_http(self) -> bool:
        parsed = urlparse(self.api_base_url)
        return parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS

    def with_admin_key(self, key: str | None) -> DashboardSettings:
        """Return settings with a validated key, or without one when blank."""

        normalized = (key or "").strip()
        if not normalized:
            return replace(self, admin_api_key=None)
        if any(char.isspace() for char in normalized):
            raise DashboardConfigurationError(
                "The admin API key must not contain whitespace."
            )
        if not 16 <= len(normalized) <= 512:
            raise DashboardConfigurationError(
                "The admin API key must be between 16 and 512 characters."
            )
        return replace(self, admin_api_key=SecretStr(normalized))

    def api_url(self, path: str) -> str:
        if not _PATH.fullmatch(path) or ".." in path:
            raise DashboardConfigurationError("Invalid dashboard API path.")
        return f"{self.api_base_url}{self.api_prefix}{path}"

    def origin_url(self, path: str) -> str:
        """Build a URL outside the versioned API prefix, such as health."""

        if not _PATH.fullmatch(path) or ".." in path:
            raise DashboardConfigurationError("Invalid dashboard API path.")
        return f"{self.api_base_url}{path}"


def load_dashboard_settings(
    environ: Mapping[str, str] | None = None,
) -> DashboardSettings:
    """Load dashboard settings without reading application settings."""

    source = os.environ if environ is None else environ
    base_url = source.get("DASHBOARD_API_BASE_URL", "http://127.0.0.1:8000")
    prefix = source.get("DASHBOARD_API_PREFIX", "/api/v1")
    timeout_raw = source.get("DASHBOARD_REQUEST_TIMEOUT_SECONDS", "10")
    try:
        timeout = float(timeout_raw)
    except ValueError:
        raise DashboardConfigurationError(
            "DASHBOARD_REQUEST_TIMEOUT_SECONDS must be a number."
        ) from None
    trust_env = _env_bool(
        source.get("DASHBOARD_TRUST_ENV", "false"), "DASHBOARD_TRUST_ENV"
    )
    settings = DashboardSettings(
        api_base_url=base_url,
        api_prefix=prefix,
        request_timeout_seconds=timeout,
        trust_env=trust_env,
    )
    return settings.with_admin_key(source.get("DASHBOARD_ADMIN_API_KEY", ""))
