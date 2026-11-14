"""Application-level fault-report summarization service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.budget.manager import BudgetManager
from app.core.config import Settings
from app.faults.extraction import extract_fault_summary
from app.faults.models import (
    ExtractionMode,
    FaultSummary,
    is_empty_summary,
    summarize_fields,
)
from app.faults.parsing import FaultSummaryParseError, parse_fault_summary
from app.faults.prompts import build_fault_messages
from app.providers.errors import (
    ProviderError,
    ProviderInvalidRequestError,
    ProviderNotFoundError,
)
from app.reliability.router import ProviderRouter

logger = logging.getLogger("app.faults.service")

_ZERO = Decimal("0.000000")


@dataclass(frozen=True)
class FaultSummaryResult:
    summary: FaultSummary
    extraction: ExtractionMode
    extraction_reason: str | None
    selected_provider: str
    provider: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Decimal
    retry_count: int
    fallback_used: bool
    fallback_reason: str | None
    providers_tried: tuple[str, ...]
    missing_fields: tuple[str, ...]


class FaultReportService:
    """Turn a maintenance report into validated structured data.

    A valid AI JSON response wins. Any unusable AI response, exhausted provider
    chain, or provider failure falls back to deterministic extraction. Client
    selection errors (unknown provider or unsupported model), authentication,
    rate limits, and budget rejections are never masked.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        provider_router: ProviderRouter,
        budget_manager: BudgetManager,
    ) -> None:
        self._settings = settings
        self._router = provider_router
        self._budget = budget_manager

    async def summarize(
        self,
        *,
        report: str,
        provider: str | None,
        model: str | None,
        request_id: str,
    ) -> FaultSummaryResult:
        selected_provider = provider or self._settings.default_provider

        try:
            route = await self._router.generate(
                selected_provider=selected_provider,
                model=model,
                messages=build_fault_messages(report),
                temperature=0.0,
                max_tokens=self._settings.fault_report_max_tokens,
                request_id=request_id,
            )
        except (ProviderNotFoundError, ProviderInvalidRequestError):
            raise
        except ProviderError as error:
            retry_count = int(getattr(error, "route_retry_count", 0))
            providers_tried = tuple(
                getattr(error, "route_providers_tried", ())
            )
            logger.warning(
                "fault_report.provider_failed",
                extra={
                    "event": "fault_report.provider_failed",
                    "request_id": request_id,
                    "selected_provider": selected_provider,
                    "error_code": error.code,
                    "retry_count": retry_count,
                    "providers_tried": list(providers_tried),
                },
            )
            summary = extract_fault_summary(report)
            return FaultSummaryResult(
                summary=summary,
                extraction="deterministic",
                extraction_reason=error.code,
                selected_provider=selected_provider,
                provider=None,
                model=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_usd=_ZERO,
                retry_count=retry_count,
                fallback_used=len(providers_tried) > 1,
                fallback_reason=(
                    error.code if len(providers_tried) > 1 else None
                ),
                providers_tried=providers_tried,
                missing_fields=summarize_fields(summary),
            )

        usage = route.result.usage
        cost = self._budget.actual_cost(route.result.provider, usage)

        try:
            summary = parse_fault_summary(route.result.content)
        except FaultSummaryParseError as error:
            summary = extract_fault_summary(report)
            extraction: ExtractionMode = "deterministic"
            reason: str | None = error.reason
            logger.warning(
                "fault_report.extraction_fallback",
                extra={
                    "event": "fault_report.extraction_fallback",
                    "request_id": request_id,
                    "provider": route.result.provider,
                    "reason": reason,
                },
            )
        else:
            extraction = "provider"
            reason = None
            if is_empty_summary(summary):
                extracted = extract_fault_summary(report)
                if not is_empty_summary(extracted):
                    summary = extracted
                    extraction = "deterministic"
                    reason = "ai_empty_summary"
                    logger.warning(
                        "fault_report.extraction_fallback",
                        extra={
                            "event": "fault_report.extraction_fallback",
                            "request_id": request_id,
                            "provider": route.result.provider,
                            "reason": reason,
                        },
                    )

        return FaultSummaryResult(
            summary=summary,
            extraction=extraction,
            extraction_reason=reason,
            selected_provider=route.requested_provider,
            provider=route.result.provider,
            model=route.result.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=cost,
            retry_count=route.retry_count,
            fallback_used=route.fallback_used,
            fallback_reason=route.fallback_reason,
            providers_tried=route.providers_tried,
            missing_fields=summarize_fields(summary),
        )
