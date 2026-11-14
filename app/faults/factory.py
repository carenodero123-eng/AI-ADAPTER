"""Build the fault-report summarizer from application components."""

from __future__ import annotations

from app.budget.manager import BudgetManager
from app.core.config import Settings
from app.faults.service import FaultReportService
from app.reliability.router import ProviderRouter


def build_fault_report_service(
    settings: Settings,
    provider_router: ProviderRouter,
    budget_manager: BudgetManager,
) -> FaultReportService:
    return FaultReportService(
        settings=settings,
        provider_router=provider_router,
        budget_manager=budget_manager,
    )
