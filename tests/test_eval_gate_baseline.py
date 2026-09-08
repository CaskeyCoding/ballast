"""EVAL-23: the gate's latency/cost bands only compare like-for-like golden-set workloads.

A p95 measured over a 43-record set says nothing about a p95 over an 89-record set with a
different category mix, so when the recorded case count differs (or the older entry predates
`n` recording), the latency/cost baseline is dropped for that one transition and the note says
so. The quality-rate comparisons and the absolute floors are never skipped.
"""

from __future__ import annotations

from ballast.eval.gate import WORKLOAD_BOUND_METRICS, baseline_for_comparison, check_gate

_TH = {
    "hallucination_rate_max": 0.05,
    "refusal_correctness_min": 0.90,
    "latency_p95_regress_frac": 0.20,
    "injection_block_rate_min": 0.95,
}


def _entry(metrics: dict[str, float], n: int | None = None) -> dict[str, object]:
    entry: dict[str, object] = {"sha": "abc1234", "metrics": metrics}
    if n is not None:
        entry["n"] = n
    return entry


_METRICS = {"hallucination_rate": 0.01, "p95_latency_s": 10.0, "mean_cost_usd": 0.006}


def test_same_workload_keeps_the_full_baseline() -> None:
    prev, note = baseline_for_comparison(_entry(_METRICS, n=89), _entry(_METRICS, n=89))
    assert prev == _METRICS
    assert note is None


def test_workload_change_drops_only_latency_and_cost() -> None:
    prev, note = baseline_for_comparison(_entry(_METRICS, n=89), _entry(_METRICS, n=43))
    assert prev is not None
    assert note is not None and "workload changed" in note
    for metric in WORKLOAD_BOUND_METRICS:
        assert metric not in prev
    assert prev["hallucination_rate"] == 0.01  # quality rates still compared


def test_unrecorded_previous_n_drops_latency_and_cost() -> None:
    prev, note = baseline_for_comparison(_entry(_METRICS, n=89), _entry(_METRICS))
    assert prev is not None and "p95_latency_s" not in prev
    assert note is not None


def test_check_gate_skips_latency_band_without_a_comparable_baseline() -> None:
    metrics = {"hallucination_rate": 0.0, "refusal_accuracy": 1.0, "p95_latency_s": 13.0}
    prev, _ = baseline_for_comparison(_entry(metrics, n=89), _entry({"p95_latency_s": 10.0}, n=43))
    assert check_gate(metrics, _TH, previous=prev) == []


def test_check_gate_still_enforces_latency_band_on_same_workload() -> None:
    metrics = {"hallucination_rate": 0.0, "refusal_accuracy": 1.0, "p95_latency_s": 13.0}
    prev, _ = baseline_for_comparison(_entry(metrics, n=89), _entry({"p95_latency_s": 10.0}, n=89))
    failures = check_gate(metrics, _TH, previous=prev)
    assert any("latency" in f for f in failures)


def test_absolute_floors_never_skipped() -> None:
    metrics = {
        "hallucination_rate": 0.20,
        "refusal_accuracy": 0.50,
        "injection_block_rate": 0.50,
        "p95_latency_s": 5.0,
    }
    prev, _ = baseline_for_comparison(_entry(metrics, n=89), _entry(_METRICS, n=43))
    failures = check_gate(metrics, _TH, previous=prev)
    assert any("hallucination" in f for f in failures)
    assert any("refusal" in f for f in failures)
    assert any("injection block rate" in f for f in failures)
