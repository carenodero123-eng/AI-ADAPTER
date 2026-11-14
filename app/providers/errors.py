"""Provider-independent error taxonomy.

Adapters translate vendor-specific failures into these errors. Application
code, reliability components, and API handlers depend only on this taxonomy.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for every normalized provider failure."""

    code = "provider_error"
    retryable = False

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider


class ProviderNotFoundError(ProviderError):
    code = "provider_not_found"


class ProviderInvalidRequestError(ProviderError):
    code = "provider_invalid_request"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"
    retryable = True


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit"
    retryable = True


class ProviderAuthenticationError(ProviderError):
    code = "provider_authentication_failed"


class ProviderServerError(ProviderError):
    code = "provider_server_error"
    retryable = True


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    retryable = True


class ProviderCircuitOpenError(ProviderUnavailableError):
    code = "provider_circuit_open"
    retryable = False


class ProviderInvalidResponseError(ProviderError):
    code = "provider_invalid_response"
    retryable = True
