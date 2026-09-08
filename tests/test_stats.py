"""EVAL-10: bootstrap confidence intervals."""

from __future__ import annotations

from ballast.eval.stats import bootstrap_ci


def test_constant_values_give_tight_interval() -> None:
    lo, hi = bootstrap_ci([1.0, 1.0, 1.0, 1.0])
    assert lo == 1.0 and hi == 1.0


def test_mixed_values_bracket_the_mean() -> None:
    values = [0.0, 1.0] * 25  # mean 0.5
    lo, hi = bootstrap_ci(values, seed=1)
    assert lo < 0.5 < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_deterministic_with_seed() -> None:
    a = bootstrap_ci([0.0, 1.0, 1.0, 0.0, 1.0], seed=7)
    b = bootstrap_ci([0.0, 1.0, 1.0, 0.0, 1.0], seed=7)
    assert a == b


def test_empty_is_zero() -> None:
    assert bootstrap_ci([]) == (0.0, 0.0)
