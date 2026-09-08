"""OBS-3: usage aggregation across run traces."""

from __future__ import annotations

import pytest

from ballast.obs.usage import aggregate_usage


def _trace(model: str, cost: float, tokens: int, nodes: list[str]) -> dict:
    return {
        "calls": [{"model": model, "cost_usd": cost, "input_tokens": tokens, "output_tokens": 0}],
        "nodes": [{"name": n, "detail": ""} for n in nodes],
    }


def test_aggregate_by_model_and_node() -> None:
    traces = [
        _trace("haiku", 0.001, 100, ["retrieve", "generate"]),
        _trace("haiku", 0.002, 200, ["retrieve", "critic"]),
        _trace("sonnet", 0.010, 500, ["generate"]),
    ]
    usage = aggregate_usage(traces)

    assert usage.total_cost_usd == pytest.approx(0.013)
    assert usage.total_tokens == 800
    assert usage.by_model["haiku"]["cost_usd"] == pytest.approx(0.003)
    assert usage.by_model["haiku"]["calls"] == 2.0
    assert usage.by_model["sonnet"]["tokens"] == 500
    # node activity counts across runs
    assert usage.by_node["retrieve"] == 2
    assert usage.by_node["generate"] == 2
    assert usage.by_node["critic"] == 1


def test_empty_traces() -> None:
    usage = aggregate_usage([])
    assert usage.total_cost_usd == 0.0 and usage.by_model == {}
