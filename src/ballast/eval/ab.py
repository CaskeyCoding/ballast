"""Prompt A/B harness (EVAL-17): compare two named prompt versions and report the metric delta.

Each version runs over the golden set; the delta (B - A) per metric is reported, and a change is
called significant only when it exceeds the noise band (the larger of the two CI half-widths).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_KEYS = ("hallucination_rate", "faithfulness_mean", "answer_relevancy_mean", "mean_cost_usd")


def deltas(
    a: Mapping[str, float], b: Mapping[str, float], keys: Sequence[str] = _KEYS
) -> dict[str, float]:
    """Per-metric change from version A to version B."""
    return {k: b[k] - a[k] for k in keys if k in a and k in b}


def is_significant(
    delta: float,
    interval_a: Sequence[float] | None,
    interval_b: Sequence[float] | None,
    *,
    margin: float = 0.02,
) -> bool:
    """A change is significant when it exceeds the larger CI half-width (or a margin)."""
    half = max(
        (interval_a[1] - interval_a[0]) / 2 if interval_a else 0.0,
        (interval_b[1] - interval_b[0]) / 2 if interval_b else 0.0,
        margin,
    )
    return abs(delta) > half


def render(
    name_a: str,
    name_b: str,
    a: Mapping[str, float],
    b: Mapping[str, float],
    intervals_a: Mapping[str, Sequence[float]] | None = None,
    intervals_b: Mapping[str, Sequence[float]] | None = None,
) -> str:
    lines = [
        f"prompt A = {name_a}   prompt B = {name_b}",
        f"{'metric':<24}{'A':>10}{'B':>10}{'delta':>10}  sig",
    ]
    for key, delta in deltas(a, b).items():
        ia = intervals_a.get(key) if intervals_a else None
        ib = intervals_b.get(key) if intervals_b else None
        sig = "*" if is_significant(delta, ia, ib) else ""
        lines.append(f"{key:<24}{a[key]:>10.4f}{b[key]:>10.4f}{delta:>+10.4f}  {sig}")
    return "\n".join(lines)
