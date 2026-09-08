"""EVAL-12: CI-aware regression detection vs the previous run."""

from __future__ import annotations

from ballast.eval.regression import detect_regressions


def test_hallucination_rise_beyond_band_flagged() -> None:
    flags = detect_regressions(
        {"hallucination_rate": 0.20}, {"hallucination_rate": 0.02}, margin=0.05
    )
    assert any("hallucination_rate rose" in f for f in flags)


def test_change_within_ci_not_flagged() -> None:
    # a hallucination move from 4% to 6% inside a wide CI is noise, not a regression
    flags = detect_regressions(
        {"hallucination_rate": 0.06},
        {"hallucination_rate": 0.04},
        intervals={"hallucination_rate": [0.0, 0.15]},  # half-width 0.075 > 0.02 move
    )
    assert flags == []


def test_faithfulness_drop_flagged() -> None:
    flags = detect_regressions(
        {"faithfulness_mean": 0.70}, {"faithfulness_mean": 0.98}, margin=0.05
    )
    assert any("faithfulness_mean dropped" in f for f in flags)


def test_improvement_not_flagged() -> None:
    flags = detect_regressions(
        {"hallucination_rate": 0.01, "faithfulness_mean": 1.0},
        {"hallucination_rate": 0.10, "faithfulness_mean": 0.8},
        margin=0.02,
    )
    assert flags == []


def test_missing_metric_ignored() -> None:
    assert detect_regressions({"foo": 1.0}, {"bar": 1.0}) == []


def test_latency_noise_band_is_proportional_not_rate_scale() -> None:
    # EVAL-23: the 0.02 fallback margin is rate-scale; 10.0s -> 11.5s sits inside the
    # 20% proportional latency band (mirroring the gate's latency_p95_regress_frac)
    assert detect_regressions({"p95_latency_s": 11.5}, {"p95_latency_s": 10.0}) == []


def test_latency_rise_beyond_proportional_band_flagged() -> None:
    flags = detect_regressions({"p95_latency_s": 12.5}, {"p95_latency_s": 10.0})
    assert any("p95_latency_s rose" in f for f in flags)


def test_cost_noise_band_is_proportional() -> None:
    # a fraction of a cent is noise, not a regression
    assert detect_regressions({"mean_cost_usd": 0.0068}, {"mean_cost_usd": 0.006}) == []
    flags = detect_regressions({"mean_cost_usd": 0.009}, {"mean_cost_usd": 0.006})
    assert any("mean_cost_usd rose" in f for f in flags)
