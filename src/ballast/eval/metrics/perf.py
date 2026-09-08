"""Performance: latency percentiles and mean cost per query, aggregated from per-query traces.

Quality is meaningless without the cost and latency it was bought at, so these are first-class.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class PerfStats:
    p50_latency_s: float
    p95_latency_s: float
    mean_cost_usd: float
    n: int


def perf_stats(latencies_s: Sequence[float], costs_usd: Sequence[float]) -> PerfStats:
    if not latencies_s:
        return PerfStats(0.0, 0.0, 0.0, 0)
    lat = np.asarray(latencies_s, dtype=np.float64)
    return PerfStats(
        p50_latency_s=float(np.percentile(lat, 50)),
        p95_latency_s=float(np.percentile(lat, 95)),
        mean_cost_usd=float(np.mean(costs_usd)) if costs_usd else 0.0,
        n=len(latencies_s),
    )
