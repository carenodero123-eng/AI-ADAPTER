"""Liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from app.api.schemas.responses import HealthResponse, ReadinessResponse
from app.api.utils import uptime_seconds
from app.core.config import Settings

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse, summary="Liveness probe")
async def liveness(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=uptime_seconds(request),
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    checks = {
        "configuration": "ok",
        "logging": "ok" if logging.getLogger().handlers else "degraded",
    }
    if getattr(request.app.state, "model_catalog", None) is not None:
        checks["models"] = "ok"
    request_log_service = getattr(
        request.app.state, "request_log_service", None
    )
    if request_log_service is not None and request_log_service.enabled:
        checks["database"] = (
            "ok" if await request_log_service.ping() else "unavailable"
        )
    ready = all(result == "ok" for result in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=checks,
    )
