"""Safe HTTP mapping for provider, security, and budget errors."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.errors import ApiErrorDetail, ErrorResponse
from app.api.utils import elapsed_ms
from app.budget.errors import BudgetExceededError
from app.core.errors import ApplicationError
from app.core.sanitize import sanitize
from app.database.paths import request_kind_for_path
from app.database.records import RequestLogEntry, utc_now
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderInvalidResponseError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.security.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    RateLimitExceededError,
)

logger = logging.getLogger("app.providers")

_ERROR_STATUS: dict[type[ProviderError], int] = {
    ProviderInvalidRequestError: 400,
    ProviderNotFoundError: 404,
    ProviderRateLimitError: 429,
    ProviderAuthenticationError: 502,
    ProviderInvalidResponseError: 502,
    ProviderServerError: 502,
    ProviderUnavailableError: 503,
    ProviderTimeoutError: 504,
}

PROVIDER_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": "Normalized provider error"}
    for status in sorted(set(_ERROR_STATUS.values()))
}

SECURITY_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Administrator privileges required"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
}

BUDGET_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    402: {"model": ErrorResponse, "description": "Budget limit exceeded"},
}

PERSISTENCE_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Request log record not found"},
    503: {"model": ErrorResponse, "description": "Request history unavailable"},
}

MODEL_CATALOG_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "Model catalog unavailable"},
}

MONITORING_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "Monitoring unavailable"},
}


def _status_for(error: ProviderError) -> int:
    for error_type, status_code in _ERROR_STATUS.items():
        if isinstance(error, error_type):
            return status_code
    return 502


async def _record_failure(
    request: Request,
    *,
    error_code: str,
    http_status: int,
    provider: str | None = None,
    retry_count: int = 0,
    providers_tried: tuple[str, ...] = (),
) -> None:
    kind = request_kind_for_path(request.url.path)
    service = getattr(request.app.state, "request_log_service", None)
    if kind is None or service is None:
        return

    identity = getattr(request.state, "auth_identity", None)
    await service.record(
        RequestLogEntry(
            request_id=getattr(request.state, "request_id", ""),
            kind=kind,
            occurred_at=utc_now(),
            auth_role=getattr(identity, "role", None),
            selected_provider=getattr(
                request.state, "selected_provider", None
            ),
            provider=provider,
            model=getattr(request.state, "model", None),
            duration_ms=elapsed_ms(request),
            retry_count=retry_count,
            fallback_used=len(providers_tried) > 1,
            fallback_reason=(
                error_code if len(providers_tried) > 1 else None
            ),
            providers_tried=providers_tried,
            status="error",
            error_code=error_code,
            http_status=http_status,
        )
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProviderError)
    async def provider_error_handler(
        request: Request, error: ProviderError
    ) -> JSONResponse:
        status_code = _status_for(error)
        request_id = getattr(request.state, "request_id", None)
        safe_message = str(sanitize(error.message))[:500]

        logger.warning(
            "provider.error",
            extra={
                "event": "provider.error",
                "request_id": request_id,
                "provider": error.provider,
                "error_code": error.code,
                "retryable": error.retryable,
                "status_code": status_code,
                "error_message": safe_message,
            },
        )
        await _record_failure(
            request,
            error_code=error.code,
            http_status=status_code,
            provider=error.provider,
            retry_count=int(getattr(error, "route_retry_count", 0)),
            providers_tried=tuple(
                getattr(error, "route_providers_tried", ())
            ),
        )

        body = ErrorResponse(
            error=ApiErrorDetail(
                code=error.code,
                message=safe_message,
                provider=error.provider,
                retryable=error.retryable,
            ),
            request_id=request_id,
        )
        return JSONResponse(status_code=status_code, content=body.model_dump())

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request, error: ApplicationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        safe_message = str(sanitize(error.message))[:500]

        logger.warning(
            "application.error",
            extra={
                "event": "application.error",
                "request_id": request_id,
                "error_code": error.code,
                "retryable": error.retryable,
                "status_code": error.status_code,
                "auth_role": getattr(
                    getattr(request.state, "auth_identity", None), "role", None
                ),
                "error_message": safe_message,
            },
        )
        await _record_failure(
            request,
            error_code=error.code,
            http_status=error.status_code,
        )

        body = ErrorResponse(
            error=ApiErrorDetail(
                code=error.code,
                message=safe_message,
                provider=None,
                retryable=error.retryable,
            ),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=body.model_dump(),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ):
        await _record_failure(
            request,
            error_code="request_validation_failed",
            http_status=422,
        )
        return await request_validation_exception_handler(request, error)


__all__ = [
    "BUDGET_ERROR_RESPONSES",
    "MODEL_CATALOG_ERROR_RESPONSES",
    "MONITORING_ERROR_RESPONSES",
    "PERSISTENCE_ERROR_RESPONSES",
    "PROVIDER_ERROR_RESPONSES",
    "SECURITY_ERROR_RESPONSES",
    "install_error_handlers",
    "AuthenticationRequiredError",
    "BudgetExceededError",
    "PermissionDeniedError",
    "RateLimitExceededError",
]
