"""Concurrency-safe budget reservation, settlement, and spend tracking."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.budget.errors import BudgetExceededError
from app.budget.estimation import estimate_prompt_tokens
from app.budget.pricing import PricingRates
from app.providers.schemas import ChatMessage, GenerationRequest, TokenUsage

logger = logging.getLogger("app.budget")

_ZERO = Decimal("0.000000")


@dataclass(frozen=True)
class BudgetReservation:
    provider: str
    estimated_cost_usd: Decimal
    prompt_tokens: int
    completion_tokens: int
    day: date
    month: tuple[int, int]


@dataclass(frozen=True)
class BudgetSnapshot:
    day: date
    month: tuple[int, int]
    spent_today_usd: Decimal
    reserved_today_usd: Decimal
    spent_month_usd: Decimal
    reserved_month_usd: Decimal


class BudgetManager:
    """Enforce per-request, daily, and monthly cost limits.

    Reservations happen before a provider call and include all concurrent
    in-flight work. Settlement replaces the reservation with reported usage;
    release returns it when a call produced no result. Counters are process
    local and must be shared through the persistence layer for multi-process
    deployments.
    """

    def __init__(
        self,
        *,
        pricing: Mapping[str, PricingRates],
        per_request_limit_usd: Decimal,
        daily_limit_usd: Decimal,
        monthly_limit_usd: Decimal,
        assumed_completion_tokens: int,
        enforce: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if per_request_limit_usd < 0 or daily_limit_usd < 0 or monthly_limit_usd < 0:
            raise ValueError("budget limits must not be negative")
        if assumed_completion_tokens < 1:
            raise ValueError("assumed_completion_tokens must be at least 1")

        self._pricing = dict(pricing)
        self._per_request_limit = per_request_limit_usd
        self._daily_limit = daily_limit_usd
        self._monthly_limit = monthly_limit_usd
        self._assumed_completion_tokens = assumed_completion_tokens
        self._enforce = enforce
        self._clock = clock
        self._lock = asyncio.Lock()

        now = self._clock()
        self._day = now.date()
        self._month = (now.year, now.month)
        self._spent_today = _ZERO
        self._reserved_today = _ZERO
        self._spent_month = _ZERO
        self._reserved_month = _ZERO

    @property
    def enforcement_enabled(self) -> bool:
        return self._enforce

    def rates_for(self, provider: str) -> PricingRates:
        return self._pricing.get(provider) or PricingRates.free()

    def estimate_cost(
        self,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal:
        return self.rates_for(provider).cost(prompt_tokens, completion_tokens)

    def estimate_request_cost(
        self,
        provider: str,
        messages: list[ChatMessage],
        max_tokens: int | None,
    ) -> Decimal:
        return self.estimate_cost(
            provider,
            estimate_prompt_tokens(messages),
            max_tokens or self._assumed_completion_tokens,
        )

    def actual_cost(self, provider: str, usage: TokenUsage) -> Decimal:
        return self.estimate_cost(
            provider,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

    async def reserve(
        self,
        provider: str,
        request: GenerationRequest,
        *,
        request_id: str,
    ) -> BudgetReservation:
        prompt_tokens = estimate_prompt_tokens(request.messages)
        completion_tokens = request.max_tokens or self._assumed_completion_tokens
        estimated = self.estimate_cost(provider, prompt_tokens, completion_tokens)

        if self._enforce and estimated > self._per_request_limit:
            logger.warning(
                "budget.rejected",
                extra={
                    "event": "budget.rejected",
                    "request_id": request_id,
                    "provider": provider,
                    "scope": "per_request",
                    "estimated_cost_usd": float(estimated),
                },
            )
            raise BudgetExceededError("per_request")

        async with self._lock:
            now = self._clock()
            self._rollover(now)

            if self._enforce:
                if (
                    self._spent_today + self._reserved_today + estimated
                    > self._daily_limit
                ):
                    self._reject("daily", provider, request_id, estimated)
                if (
                    self._spent_month + self._reserved_month + estimated
                    > self._monthly_limit
                ):
                    self._reject("monthly", provider, request_id, estimated)
                self._reserved_today += estimated
                self._reserved_month += estimated

            reservation = BudgetReservation(
                provider=provider,
                estimated_cost_usd=estimated,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                day=self._day,
                month=self._month,
            )

        logger.info(
            "budget.reserved",
            extra={
                "event": "budget.reserved",
                "request_id": request_id,
                "provider": provider,
                "estimated_cost_usd": float(estimated),
                "estimated_prompt_tokens": prompt_tokens,
                "estimated_completion_tokens": completion_tokens,
            },
        )
        return reservation

    async def settle(
        self,
        reservation: BudgetReservation,
        result_usage: TokenUsage,
        *,
        request_id: str,
    ) -> None:
        actual = self.actual_cost(reservation.provider, result_usage)

        async with self._lock:
            now = self._clock()
            self._rollover(now)
            if self._enforce:
                self._release_reserved(reservation)
            self._spent_today += actual
            self._spent_month += actual

        logger.info(
            "budget.settled",
            extra={
                "event": "budget.settled",
                "request_id": request_id,
                "provider": reservation.provider,
                "estimated_cost_usd": float(reservation.estimated_cost_usd),
                "cost_usd": float(actual),
                "prompt_tokens": result_usage.prompt_tokens,
                "completion_tokens": result_usage.completion_tokens,
            },
        )

    async def release(
        self,
        reservation: BudgetReservation,
        *,
        request_id: str,
    ) -> None:
        if self._enforce:
            async with self._lock:
                self._rollover(self._clock())
                self._release_reserved(reservation)

        logger.info(
            "budget.released",
            extra={
                "event": "budget.released",
                "request_id": request_id,
                "provider": reservation.provider,
                "estimated_cost_usd": float(reservation.estimated_cost_usd),
            },
        )

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            day=self._day,
            month=self._month,
            spent_today_usd=self._spent_today,
            reserved_today_usd=self._reserved_today,
            spent_month_usd=self._spent_month,
            reserved_month_usd=self._reserved_month,
        )

    def _release_reserved(self, reservation: BudgetReservation) -> None:
        if reservation.day == self._day:
            self._reserved_today = max(
                _ZERO, self._reserved_today - reservation.estimated_cost_usd
            )
        if reservation.month == self._month:
            self._reserved_month = max(
                _ZERO, self._reserved_month - reservation.estimated_cost_usd
            )

    def _reject(
        self,
        scope: str,
        provider: str,
        request_id: str,
        estimated: Decimal,
    ) -> None:
        logger.warning(
            "budget.rejected",
            extra={
                "event": "budget.rejected",
                "request_id": request_id,
                "provider": provider,
                "scope": scope,
                "estimated_cost_usd": float(estimated),
            },
        )
        raise BudgetExceededError(scope)

    def _rollover(self, now: datetime) -> None:
        today = now.date()
        month = (now.year, now.month)
        if today != self._day:
            self._day = today
            self._spent_today = _ZERO
            self._reserved_today = _ZERO
        if month != self._month:
            self._month = month
            self._spent_month = _ZERO
            self._reserved_month = _ZERO
