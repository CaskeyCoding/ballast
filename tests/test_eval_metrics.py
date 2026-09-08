"""EVAL-3/7/8: faithfulness judge, refusal correctness, latency/cost stats."""

from __future__ import annotations

import pytest

from ballast.core.config import ModelRegistry
from ballast.core.testing import FakeLLMClient
from ballast.eval.metrics.faithfulness import faithfulness_score
from ballast.eval.metrics.perf import perf_stats
from ballast.eval.metrics.refusal import is_refusal, refusal_stats
from ballast.eval.metrics.relevancy import relevancy_score
from ballast.gateway.fallback import INSUFFICIENT


# --- EVAL-3 faithfulness ---
def test_supported_answer_scores_one() -> None:
    client = FakeLLMClient(['{"supported": true, "reason": "all claims backed"}'])
    score = faithfulness_score(client, "q", "a", ["src"], registry=ModelRegistry())
    assert score == 1.0


def test_unsupported_answer_scores_zero() -> None:
    client = FakeLLMClient(['{"supported": false, "reason": "made up a number"}'])
    score = faithfulness_score(client, "q", "a", ["src"], registry=ModelRegistry())
    assert score == 0.0


# --- EVAL-4 relevancy ---
def test_relevant_answer_scores_one() -> None:
    client = FakeLLMClient(['{"relevant": true, "reason": "addresses it"}'])
    assert relevancy_score(client, "q", "a", registry=ModelRegistry()) == 1.0


def test_evasive_answer_scores_zero() -> None:
    client = FakeLLMClient(['{"relevant": false, "reason": "evasive"}'])
    assert relevancy_score(client, "q", "a", registry=ModelRegistry()) == 0.0


# --- EVAL-7 refusal ---
def test_is_refusal_detects_decline_and_fallbacks() -> None:
    assert is_refusal(INSUFFICIENT)
    assert is_refusal("Your message could not be processed: input contains card")
    assert not is_refusal("Diversification spreads risk across investments.")


def test_refusal_stats_counts_both_error_directions() -> None:
    # (should_decline, did_refuse)
    stats = refusal_stats(
        [
            (True, True),  # correct decline
            (False, False),  # correct answer
            (True, False),  # under-refused (answered when it should decline = hallucination risk)
            (False, True),  # over-refused (declined a real question)
        ]
    )
    assert stats.correct == 2
    assert stats.under_refused == 1
    assert stats.over_refused == 1
    assert stats.accuracy == 0.5


# --- EVAL-8 perf ---
def test_perf_percentiles_and_cost() -> None:
    stats = perf_stats([1.0, 2.0, 3.0, 4.0], [0.01, 0.02, 0.03, 0.04])
    assert stats.p50_latency_s == pytest.approx(2.5)
    assert stats.mean_cost_usd == pytest.approx(0.025)
    assert stats.n == 4


def test_perf_empty_is_zero() -> None:
    assert perf_stats([], []).n == 0
