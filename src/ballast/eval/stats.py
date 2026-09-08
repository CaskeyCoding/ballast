"""Bootstrap confidence intervals (EVAL-10).

A 4% vs 6% hallucination move on a few dozen questions can be pure noise. A bootstrap CI on the mean
of the per-case values shows how much of the point estimate to trust, so the regression check (and a
human reader) does not chase noise. Seeded for determinism.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def bootstrap_ci(
    values: Sequence[float], *, n_resamples: int = 1000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile confidence interval for the mean of `values` via resampling."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=np.float64)
    means = np.array(
        [rng.choice(arr, size=arr.size, replace=True).mean() for _ in range(n_resamples)]
    )
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (lo, hi)
