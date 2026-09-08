"""Regression detection vs the last committed run (EVAL-12).

A metric is flagged only when it moves in the bad direction by more than the noise band, where the
band is the metric's confidence-interval half-width (EVAL-10), falling back to a configured margin.
This keeps the gate from chasing run-to-run judge noise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# metric -> "down" means higher-is-better (a drop is a regression); "up" means lower-is-better.
_DIRECTION: dict[str, str] = {
    "faithfulness_mean": "down",
    "answer_relevancy_mean": "down",
    "refusal_accuracy": "down",
    "injection_block_rate": "down",
    "hallucination_rate": "up",
    "p95_latency_s": "up",
    "mean_cost_usd": "up",
}

# The default margin is sized for 0-1 rates. Latency (seconds) and cost (dollars) live on
# arbitrary scales where an absolute 0.02 would flag pure run-to-run noise, so their fallback
# band is proportional to the previous value, mirroring the gate's latency_p95_regress_frac
# design (core.config.DEFAULT_THRESHOLDS).
_SCALE_METRIC_FRAC: dict[str, float] = {"p95_latency_s": 0.20, "mean_cost_usd": 0.20}


def _band(interval: Sequence[float] | None, margin: float) -> float:
    half_width = (interval[1] - interval[0]) / 2 if interval else 0.0
    return max(half_width, margin)


def detect_regressions(
    latest: Mapping[str, float],
    previous: Mapping[str, float],
    *,
    intervals: Mapping[str, Sequence[float]] | None = None,
    margin: float = 0.02,
) -> list[str]:
    flags: list[str] = []
    for metric, direction in _DIRECTION.items():
        if metric not in latest or metric not in previous:
            continue
        cur, prev = latest[metric], previous[metric]
        frac = _SCALE_METRIC_FRAC.get(metric)
        fallback = abs(prev) * frac if frac is not None else margin
        band = _band(intervals.get(metric) if intervals else None, fallback)
        drop = prev - cur
        rise = cur - prev
        if direction == "down" and drop > band:
            flags.append(f"{metric} dropped {prev:.3f} -> {cur:.3f} (beyond noise band {band:.3f})")
        elif direction == "up" and rise > band:
            flags.append(f"{metric} rose {prev:.3f} -> {cur:.3f} (beyond noise band {band:.3f})")
    return flags
