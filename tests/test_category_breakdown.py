"""EVAL-11: per-category metric breakdown."""

from __future__ import annotations

from ballast.eval.runner import CaseResult, category_breakdown


def _case(cat: str, *, decline: bool, refused: bool, faith: float | None) -> CaseResult:
    return CaseResult(
        id="x",
        category=cat,
        should_decline=decline,
        refused=refused,
        faithfulness=faith,
        latency_s=1.0,
        cost_usd=0.01,
    )


def test_breakdown_isolates_a_per_category_regression() -> None:
    cases = [
        _case("answerable", decline=False, refused=False, faith=1.0),  # clean
        _case("answerable", decline=False, refused=False, faith=1.0),  # clean
        _case("adversarial", decline=True, refused=False, faith=0.0),  # under-refused -> halluc
    ]
    bd = category_breakdown(cases)
    assert bd["answerable"]["hallucination_rate"] == 0.0
    assert bd["adversarial"]["hallucination_rate"] == 1.0  # not averaged away by the clean ones
    assert bd["answerable"]["count"] == 2.0
    assert bd["adversarial"]["refusal_accuracy"] == 0.0  # it answered when it should decline
