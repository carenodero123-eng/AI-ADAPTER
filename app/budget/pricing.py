"""Provider-specific token pricing."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

_MILLION = Decimal(1_000_000)
_MICRO_DOLLAR = Decimal("0.000001")


class PricingRates(BaseModel):
    """USD prices per one million input and output tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_per_million_usd: Decimal = Field(ge=0)
    output_per_million_usd: Decimal = Field(ge=0)

    @classmethod
    def free(cls) -> PricingRates:
        return cls(
            input_per_million_usd=Decimal("0"),
            output_per_million_usd=Decimal("0"),
        )

    def cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        total = (
            Decimal(prompt_tokens) * self.input_per_million_usd
            + Decimal(completion_tokens) * self.output_per_million_usd
        ) / _MILLION
        return total.quantize(_MICRO_DOLLAR)
