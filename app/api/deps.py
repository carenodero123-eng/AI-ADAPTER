"""Typed FastAPI dependencies backed by application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response

from app.budget.manager import BudgetManager
from app.core.config import Settings
from app.database.service import RequestLogService
from app.faults.service import FaultReportService
from app.model_catalog.versions import ModelCatalog
from app.monitoring.metrics import MetricsCollector
from app.monitoring.service import MonitoringService
from app.providers.registry import ProviderRegistry
from app.reliability.router import ProviderRouter
from app.security.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
)
from app.security.manager import SecurityManager
from app.security.models import AuthIdentity
from app.security.rate_limit import RateLimiter


def get_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


def get_provider_router(request: Request) -> ProviderRouter:
    return request.app.state.provider_router


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_security_manager(request: Request) -> SecurityManager:
    return request.app.state.security_manager


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_budget_manager(request: Request) -> BudgetManager:
    return request.app.state.budget_manager


def get_fault_report_service(request: Request) -> FaultReportService:
    return request.app.state.fault_report_service


def get_request_log_service(request: Request) -> RequestLogService:
    return request.app.state.request_log_service


def get_model_catalog(request: Request) -> ModelCatalog | None:
    return getattr(request.app.state, "model_catalog", None)


def get_monitoring_service(request: Request) -> MonitoringService:
    return request.app.state.monitoring_service


def get_metrics_collector(request: Request) -> MetricsCollector:
    return request.app.state.metrics_collector


RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]
ProviderRouterDep = Annotated[ProviderRouter, Depends(get_provider_router)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SecurityManagerDep = Annotated[SecurityManager, Depends(get_security_manager)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
BudgetManagerDep = Annotated[BudgetManager, Depends(get_budget_manager)]
FaultReportServiceDep = Annotated[
    FaultReportService, Depends(get_fault_report_service)
]
RequestLogServiceDep = Annotated[
    RequestLogService, Depends(get_request_log_service)
]
ModelCatalogDep = Annotated[ModelCatalog | None, Depends(get_model_catalog)]
MonitoringServiceDep = Annotated[
    MonitoringService, Depends(get_monitoring_service)
]
MetricsCollectorDep = Annotated[
    MetricsCollector, Depends(get_metrics_collector)
]


def _bearer_token(header: str | None) -> str:
    if not header:
        raise AuthenticationRequiredError()
    scheme, separator, token = header.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise AuthenticationRequiredError()
    token = token.strip()
    if not token or any(char.isspace() for char in token):
        raise AuthenticationRequiredError()
    return token


async def _resolve_identity(
    request: Request,
    response: Response,
    settings: Settings,
    security: SecurityManager,
    rate_limiter: RateLimiter,
    *,
    admin: bool,
) -> AuthIdentity:
    if settings.security_require_auth:
        identity = security.authenticate(
            _bearer_token(request.headers.get("Authorization"))
        )
        if identity is None:
            raise AuthenticationRequiredError()
        if admin and identity.role != "admin":
            raise PermissionDeniedError()
    else:
        host = request.client.host if request.client else "unknown"
        identity = AuthIdentity(role="anonymous", rate_limit_key=f"ip:{host}")

    request.state.auth_identity = identity
    decision = await rate_limiter.check(identity.rate_limit_key)
    if decision is not None:
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    return identity


async def require_api_user(
    request: Request,
    response: Response,
    settings: SettingsDep,
    security: SecurityManagerDep,
    rate_limiter: RateLimiterDep,
) -> AuthIdentity:
    return await _resolve_identity(
        request, response, settings, security, rate_limiter, admin=False
    )


async def require_admin(
    request: Request,
    response: Response,
    settings: SettingsDep,
    security: SecurityManagerDep,
    rate_limiter: RateLimiterDep,
) -> AuthIdentity:
    return await _resolve_identity(
        request, response, settings, security, rate_limiter, admin=True
    )


AuthIdentityDep = Annotated[AuthIdentity, Depends(require_api_user)]
AdminDep = Annotated[AuthIdentity, Depends(require_admin)]
