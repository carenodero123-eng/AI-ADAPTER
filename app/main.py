"""FastAPI application factory and Uvicorn entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.budget.factory import build_budget_manager
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.factory import build_database, build_request_log_service
from app.faults.factory import build_fault_report_service
from app.model_catalog.errors import ModelCatalogConfigurationError
from app.model_catalog.factory import build_model_catalog
from app.monitoring.factory import build_metrics_collector, build_monitoring_service
from app.providers.factory import build_provider_registry
from app.providers.registry import ProviderRegistry
from app.reliability.factory import build_provider_router
from app.reliability.router import ProviderRouter
from app.security.factory import build_rate_limiter, build_security_manager

logger = logging.getLogger("app.lifecycle")


def create_app(
    settings: Settings | None = None,
    *,
    registry: ProviderRegistry | None = None,
    provider_router: ProviderRouter | None = None,
) -> FastAPI:
    """Build a fully configured application instance."""

    settings = settings or get_settings()
    configure_logging(settings)

    if registry is None:
        registry = build_provider_registry(settings)
    elif settings.default_provider not in registry:
        raise ValueError(
            f"DEFAULT_PROVIDER '{settings.default_provider}' is not registered; "
            f"available providers: {', '.join(registry.names)}"
        )

    try:
        model_catalog = build_model_catalog(settings, registry)
    except ModelCatalogConfigurationError as error:
        logger.error(
            "model_catalog.load_failed",
            extra={
                "event": "model_catalog.load_failed",
                "error_type": type(error).__name__,
            },
        )
        raise

    security_manager = build_security_manager(settings)
    rate_limiter = build_rate_limiter(settings)
    budget_manager = build_budget_manager(settings, registry)

    if provider_router is None:
        provider_router = build_provider_router(settings, registry, budget=budget_manager)

    fault_report_service = build_fault_report_service(
        settings, provider_router, budget_manager
    )
    database = build_database(settings)
    metrics_collector = build_metrics_collector()
    request_log_service = build_request_log_service(
        settings, database, observer=metrics_collector.observe
    )
    monitoring_service = build_monitoring_service(settings, database)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if database is not None:
            try:
                await database.initialize()
            except Exception as error:
                logger.error(
                    "database.initialization_failed",
                    extra={
                        "event": "database.initialization_failed",
                        "database_dialect": database.dialect,
                        "error_type": type(error).__name__,
                    },
                )
                await database.dispose()
                raise
        logger.info(
            "application.started",
            extra={
                "event": "application.started",
                "service": settings.app_name,
                "version": settings.app_version,
                "environment": settings.environment,
                "providers": list(registry.names),
                "secondary_provider": provider_router.secondary_provider,
                "fallback_provider": provider_router.fallback_provider,
                "retry_max_attempts": settings.reliability_max_attempts,
                "circuit_failure_threshold": (
                    settings.reliability_circuit_failure_threshold
                ),
                "auth_required": settings.security_require_auth,
                "user_key_count": security_manager.user_key_count,
                "admin_key_count": security_manager.admin_key_count,
                "rate_limit_requests": settings.security_rate_limit_requests,
                "rate_limit_window_seconds": (
                    settings.security_rate_limit_window_seconds
                ),
                "budget_enforcement": budget_manager.enforcement_enabled,
                "budget_daily_usd": float(settings.budget_daily_usd),
                "budget_monthly_usd": float(settings.budget_monthly_usd),
                "fault_report_max_tokens": settings.fault_report_max_tokens,
                "database_enabled": database is not None,
                "database_dialect": (
                    database.dialect if database is not None else None
                ),
                "database_auto_create": settings.database_auto_create,
                "monitoring_reporting_enabled": monitoring_service.enabled,
                "monitoring_latency_sample_limit": (
                    settings.monitoring_latency_sample_limit
                ),
                "monitoring_query_timeout_seconds": (
                    settings.monitoring_query_timeout_seconds
                ),
                "model_catalog_enabled": model_catalog is not None,
                "model_catalog_entries": (
                    len(model_catalog.entries) if model_catalog is not None else 0
                ),
                "model_catalog_status_counts": (
                    model_catalog.status_counts()
                    if model_catalog is not None
                    else {}
                ),
            },
        )
        try:
            yield
        finally:
            await registry.aclose()
            if database is not None:
                await database.dispose()
            logger.info(
                "application.stopped",
                extra={"event": "application.stopped", "service": settings.app_name},
            )

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Provider-independent AI adapter service.",
        debug=settings.debug,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.provider_registry = registry
    app.state.provider_router = provider_router
    app.state.model_catalog = model_catalog
    app.state.security_manager = security_manager
    app.state.rate_limiter = rate_limiter
    app.state.budget_manager = budget_manager
    app.state.fault_report_service = fault_report_service
    app.state.database = database
    app.state.request_log_service = request_log_service
    app.state.metrics_collector = metrics_collector
    app.state.monitoring_service = monitoring_service
    app.state.started_at = datetime.now(UTC)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", settings.request_id_header],
        expose_headers=[
            settings.request_id_header,
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "Retry-After",
        ],
    )
    app.add_middleware(RequestContextMiddleware, header_name=settings.request_id_header)

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
