"""Build the budget manager from validated settings and the registry."""

from __future__ import annotations

import logging
from decimal import Decimal

from app.budget.manager import BudgetManager
from app.core.config import Settings
from app.providers.registry import ProviderRegistry

logger = logging.getLogger("app.budget")


def build_budget_manager(
    settings: Settings,
    registry: ProviderRegistry,
) -> BudgetManager:
    pricing = {
        name: settings.budget_provider_pricing[name]
        for name in registry.names
        if name in settings.budget_provider_pricing
    }
    for name in registry.names:
        if name not in pricing:
            logger.warning(
                "budget.pricing.missing",
                extra={
                    "event": "budget.pricing.missing",
                    "provider": name,
                    "fallback_cost": "zero",
                },
            )

    return BudgetManager(
        pricing=pricing,
        per_request_limit_usd=Decimal(settings.budget_per_request_usd),
        daily_limit_usd=Decimal(settings.budget_daily_usd),
        monthly_limit_usd=Decimal(settings.budget_monthly_usd),
        assumed_completion_tokens=settings.budget_assumed_completion_tokens,
        enforce=settings.budget_enforcement_enabled,
    )
