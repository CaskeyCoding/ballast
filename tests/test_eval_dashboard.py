"""EVAL-15: the dashboard renders from a fixture ledger with no external dependency."""

from __future__ import annotations

from ballast.eval.dashboard import build_dashboard


def test_dashboard_renders_metrics_and_trend() -> None:
    history = [
        {
            "sha": "a",
            "metrics": {
                "hallucination_rate": 0.10,
                "refusal_accuracy": 0.8,
                "p95_latency_s": 9.0,
                "mean_cost_usd": 0.02,
                "faithfulness_mean": 0.9,
            },
        },
        {
            "sha": "b",
            "metrics": {
                "hallucination_rate": 0.04,
                "refusal_accuracy": 0.95,
                "p95_latency_s": 8.0,
                "mean_cost_usd": 0.015,
                "faithfulness_mean": 0.96,
            },
        },
    ]
    html = build_dashboard(history)
    assert "Hallucination rate" in html
    assert "Refusal correctness" in html
    assert "<polyline" in html  # a trend line was drawn
    assert "2 run(s)" in html
    assert "http" not in html.replace("https://www.w3.org", "")  # no external CDN/resources


def test_dashboard_handles_empty_series() -> None:
    html = build_dashboard([{"sha": "a", "metrics": {}}])
    assert "n/a" in html
