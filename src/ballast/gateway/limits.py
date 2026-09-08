"""Input size guard (SEC-3): reject oversized inputs before they reach the model.

An unbounded input can exhaust cost or memory. This pre-hook caps input length; the per-run spend
cap is enforced separately by core.cost.CostMeter (BudgetExceeded), so the two DoS/cost guards
sit on the two axes (size and spend).
"""

from __future__ import annotations

from ballast.gateway.types import HookResult, Request


class SizeGuard:
    name = "size-limit"

    def __init__(self, max_chars: int = 8000) -> None:
        self.max_chars = max_chars

    def check(self, request: Request) -> HookResult:
        n = len(request.question)
        if n > self.max_chars:
            return HookResult.block("size-limit", f"input is {n} chars (max {self.max_chars})")
        return HookResult.allow()
