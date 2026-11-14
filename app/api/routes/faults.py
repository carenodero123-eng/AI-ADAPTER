"""Structured fault-report summarization endpoint."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request

from app.api.deps import (
    AuthIdentityDep,
    FaultReportServiceDep,
    RequestLogServiceDep,
    SettingsDep,
)
from app.api.errors import (
    BUDGET_ERROR_RESPONSES,
    PROVIDER_ERROR_RESPONSES,
    SECURITY_ERROR_RESPONSES,
)
from app.api.schemas.faults import FaultReportRequest, FaultSummaryResponse
from app.database.records import RequestLogEntry, utc_now

logger = logging.getLogger("app.api.faults")

router = APIRouter(tags=["faults"])


@router.post(
    "/fault-reports/summarize",
    response_model=FaultSummaryResponse,
    responses={
        **PROVIDER_ERROR_RESPONSES,
        **SECURITY_ERROR_RESPONSES,
        **BUDGET_ERROR_RESPONSES,
    },
    summary="Summarize a fault report into validated structured data",
)
async def summarize_fault_report(
    payload: FaultReportRequest,
    request: Request,
    identity: AuthIdentityDep,
    service: FaultReportServiceDep,
    request_log: RequestLogServiceDep,
    settings: SettingsDep,
) -> FaultSummaryResponse:
    started = time.perf_counter()
    selected_provider = payload.provider or settings.default_provider
    request.state.selected_provider = selected_provider
    request.state.model = payload.model
    result = await service.summarize(
        report=payload.report,
        provider=payload.provider,
        model=payload.model,
        request_id=request.state.request_id,
    )

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    final_status = "success" if result.extraction == "provider" else "degraded"
    await request_log.record(
        RequestLogEntry(
            request_id=request.state.request_id,
            kind="fault_report",
            occurred_at=utc_now(),
            auth_role=identity.role,
            selected_provider=result.selected_provider,
            provider=result.provider,
            model=result.model,
            duration_ms=duration_ms,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
            retry_count=result.retry_count,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
            providers_tried=result.providers_tried,
            status=final_status,
            http_status=200,
            extraction=result.extraction,
            extraction_reason=result.extraction_reason,
            missing_field_count=len(result.missing_fields),
        )
    )

    logger.info(
        "fault_report.summary",
        extra={
            "event": "fault_report.summary",
            "request_id": request.state.request_id,
            "auth_role": identity.role,
            "requested_provider": result.selected_provider,
            "provider": result.provider,
            "model": result.model,
            "extraction": result.extraction,
            "extraction_reason": result.extraction_reason,
            "missing_field_count": len(result.missing_fields),
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "cost_usd": float(result.cost_usd),
            "retry_count": result.retry_count,
            "fallback_used": result.fallback_used,
            "fallback_reason": result.fallback_reason,
            "duration_ms": duration_ms,
            "status": final_status,
        },
    )

    return FaultSummaryResponse(
        request_id=request.state.request_id,
        summary=result.summary,
        extraction=result.extraction,
        extraction_reason=result.extraction_reason,
        missing_fields=list(result.missing_fields),
        selected_provider=result.selected_provider,
        provider=result.provider,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        cost_usd=float(result.cost_usd),
        retry_count=result.retry_count,
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        providers_tried=list(result.providers_tried),
    )
