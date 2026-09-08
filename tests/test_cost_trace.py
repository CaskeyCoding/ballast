"""CORE-6 + CORE-7: cost math, budget cap, trace serialization, metered client."""

from __future__ import annotations

import json

import pytest

from ballast.core.cost import BudgetExceeded, CostMeter, cost_usd, price_for
from ballast.core.llm import LLMClient
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import MeteredClient, Trace


def test_cost_math_known_tokens() -> None:
    # Sonnet: 3/Mtok in, 15/Mtok out. 1000 in + 1000 out = 0.003 + 0.015 = 0.018
    assert cost_usd("claude-sonnet-4-6", 1000, 1000) == pytest.approx(0.018)


def test_unknown_model_not_free() -> None:
    # Operational Lesson 1: an unpriced model must not look free.
    assert price_for("some-future-model") != (0.0, 0.0)


def test_budget_cap_trips_before_overspend() -> None:
    meter = CostMeter(cap_usd=0.01)
    meter.add("claude-sonnet-4-6", 1000, 1000)  # 0.018, now over cap
    with pytest.raises(BudgetExceeded, match="run budget"):
        meter.check()


def test_trace_serializes_and_aggregates() -> None:
    trace = Trace(run_id="r1")
    base = FakeLLMClient(["hello there"])
    metered = MeteredClient(base, CostMeter(cap_usd=1.0), trace, clock=iter([0.0, 0.25]).__next__)
    assert isinstance(metered, LLMClient)
    trace.record_node("retrieve")
    metered.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5-20251001")
    trace.record_decision("critic", "grounded", "supported")

    blob = json.dumps(trace.to_dict())
    data = json.loads(blob)
    assert data["run_id"] == "r1"
    assert data["nodes"][0]["name"] == "retrieve"
    assert len(data["calls"]) == 1
    assert data["calls"][0]["latency_s"] == pytest.approx(0.25)
    assert data["totals"]["tokens"] == trace.total_tokens
    assert data["decisions"][0]["outcome"] == "grounded"


def test_metered_client_enforces_budget() -> None:
    trace = Trace(run_id="r2")
    base = FakeLLMClient(["a", "b"])
    metered = MeteredClient(base, CostMeter(cap_usd=0.0), trace)
    with pytest.raises(BudgetExceeded):
        metered.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-4-6")
