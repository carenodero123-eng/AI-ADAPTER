"""Provider-independent generation endpoint."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request

from app.api.deps import (
    AuthIdentityDep,
    BudgetManagerDep,
    ProviderRouterDep,
    RequestLogServiceDep,
    SettingsDep,
)
from app.api.errors import (
    BUDGET_ERROR_RESPONSES,
    PROVIDER_ERROR_RESPONSES,
    SECURITY_ERROR_RESPONSES,
)
from app.api.schemas.generation import GenerateRequest, GenerateResponse
from app.database.records import RequestLogEntry, utc_now

logger = logging.getLogger("app.api.generation")

router = APIRouter(tags=["generation"])


@router.post(
    "/generate",
    response_model=GenerateResponse,
    responses={
        **PROVIDER_ERROR_RESPONSES,
        **SECURITY_ERROR_RESPONSES,
        **BUDGET_ERROR_RESPONSES,
    },
    summary="Generate through the reliable provider chain",
)
async def generate(
    payload: GenerateRequest,
    request: Request,
    identity: AuthIdentityDep,
    provider_router: ProviderRouterDep,
    budget_manager: BudgetManagerDep,
    request_log: RequestLogServiceDep,
    settings: SettingsDep,
) -> GenerateResponse:
    started = time.perf_counter()
    selected_provider = payload.provider or settings.default_provider
    request.state.selected_provider = selected_provider
    request.state.model = payload.model
    route = await provider_router.generate(
        selected_provider=selected_provider,
        model=payload.model,
        messages=payload.messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        request_id=request.state.request_id,
    )
    cost = budget_manager.actual_cost(route.result.provider, route.result.usage)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    await request_log.record(
        RequestLogEntry(
            request_id=request.state.request_id,
            kind="generation",
            occurred_at=utc_now(),
            auth_role=identity.role,
            selected_provider=route.requested_provider,
            provider=route.result.provider,
            model=route.result.model,
            duration_ms=duration_ms,
            prompt_tokens=route.result.usage.prompt_tokens,
            completion_tokens=route.result.usage.completion_tokens,
            total_tokens=route.result.usage.total_tokens,
            cost_usd=cost,
            retry_count=route.retry_count,
            fallback_used=route.fallback_used,
            fallback_reason=route.fallback_reason,
            providers_tried=route.providers_tried,
            status="success",
            http_status=200,
        )
    )

    logger.info(
        "request.summary",
        extra={
            "event": "request.summary",
            "request_id": request.state.request_id,
            "auth_role": identity.role,
            "requested_provider": route.requested_provider,
            "provider": route.result.provider,
            "model": route.result.model,
            "prompt_tokens": route.result.usage.prompt_tokens,
            "completion_tokens": route.result.usage.completion_tokens,
            "total_tokens": route.result.usage.total_tokens,
            "cost_usd": float(cost),
            "retry_count": route.retry_count,
            "fallback_used": route.fallback_used,
            "fallback_reason": route.fallback_reason,
            "duration_ms": duration_ms,
            "status": "success",
        },
    )

    return GenerateResponse(
        **route.result.model_dump(),
        request_id=request.state.request_id,
        requested_provider=route.requested_provider,
        retry_count=route.retry_count,
        fallback_used=route.fallback_used,
        fallback_reason=route.fallback_reason,
        providers_tried=list(route.providers_tried),
        cost_usd=float(cost),
    )
