"""SEC-3: the input-size guard rejects oversized inputs; the budget guard caps spend."""

from __future__ import annotations

import pytest

from ballast.core.cost import BudgetExceeded, CostMeter
from ballast.gateway.limits import SizeGuard
from ballast.gateway.types import Request


def test_oversized_input_blocked() -> None:
    guard = SizeGuard(max_chars=10)
    res = guard.check(Request("x" * 50))
    assert res.action == "block" and res.rule == "size-limit"


def test_normal_input_allowed() -> None:
    assert SizeGuard(max_chars=100).check(Request("a short question")).action == "allow"


def test_budget_guard_caps_spend() -> None:
    # the per-run cost cap raises a typed error before overspending (CORE-6, the spend axis)
    meter = CostMeter(cap_usd=0.0)
    meter.add("claude-sonnet-4-6", 1000, 1000)
    with pytest.raises(BudgetExceeded):
        meter.check()
