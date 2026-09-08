"""Token pricing and a per-run budget guard.

A price table maps model id to USD-per-million-tokens (input, output). `CostMeter` accumulates
spend across a run and raises `BudgetExceeded` before a call that would push it over the cap, so
an unattended loop or a 100-question eval cannot quietly run up a real bill. Prices are approximate
and live in one place; update them here, not at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass

# (input_usd_per_mtok, output_usd_per_mtok). Approximate list prices; adjust as they change.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "fake-model": (0.0, 0.0),
}

# Unknown models fall back to Sonnet-class pricing rather than 0, so an unpriced model never
# silently looks free (Operational Lesson 1: never collapse a missing value to zero).
_FALLBACK_PRICE = (3.0, 15.0)


def price_for(model: str) -> tuple[float, float]:
    return PRICE_TABLE.get(model, _FALLBACK_PRICE)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_for(model)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


class BudgetExceeded(RuntimeError):
    """Raised when a run's accumulated LLM cost would exceed its configured cap."""


@dataclass
class CostMeter:
    """Accumulates spend for one run and enforces a hard USD cap."""

    cap_usd: float
    spent_usd: float = 0.0

    def check(self) -> None:
        """Raise if we are already at or over the cap (called before each new call)."""
        if self.spent_usd >= self.cap_usd:
            raise BudgetExceeded(
                f"run budget ${self.cap_usd:.4f} reached (spent ${self.spent_usd:.4f})"
            )

    def add(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Record the cost of a completed call and return it."""
        c = cost_usd(model, input_tokens, output_tokens)
        self.spent_usd += c
        return c
