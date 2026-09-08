"""EVAL-5: context precision and recall."""

from __future__ import annotations

from ballast.eval.metrics.retrieval import (
    ContextScore,
    context_scores,
    mean_context,
    source_of,
)


def test_precision_and_recall() -> None:
    # surfaced {a, b}, relevant {a}: precision 1/2, recall 1/1
    s = context_scores({"a", "b"}, {"a"})
    assert s.precision == 0.5 and s.recall == 1.0
    # surfaced {a}, relevant {a, b}: precision 1/1, recall 1/2
    s = context_scores({"a"}, {"a", "b"})
    assert s.precision == 1.0 and s.recall == 0.5


def test_empty_cases() -> None:
    assert context_scores(set(), {"a"}).precision == 0.0  # nothing surfaced
    assert context_scores({"a"}, set()) == ContextScore(1.0, 1.0)  # nothing expected


def test_mean_context() -> None:
    m = mean_context([ContextScore(1.0, 0.5), ContextScore(0.0, 0.5)])
    assert m.precision == 0.5 and m.recall == 0.5
    assert mean_context([]) == ContextScore(1.0, 1.0)


def test_source_of() -> None:
    assert source_of("diversification#3") == "diversification"
    assert source_of("nohash") == "nohash"
