"""Non-secret service metadata for clients and the future dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.responses import SystemInfoResponse
from app.api.utils import uptime_seconds
from app.core.config import Settings

router = APIRouter(tags=["system"])


@router.get("/system/info", response_model=SystemInfoResponse, summary="Service metadata")
async def system_info(request: Request) -> SystemInfoResponse:
    settings: Settings = request.app.state.settings
    return SystemInfoResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_prefix=settings.api_prefix,
        docs_url=request.app.docs_url,
        uptime_seconds=uptime_seconds(request),
    )
