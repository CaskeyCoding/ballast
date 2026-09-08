"""EVAL-17: prompt registry + A/B delta and significance."""

from __future__ import annotations

import pytest

from ballast.eval.ab import deltas, is_significant, render
from ballast.rag.prompts import GENERATION_PROMPTS, get_prompt


def test_prompt_registry() -> None:
    assert "default" in GENERATION_PROMPTS and "concise" in GENERATION_PROMPTS
    assert get_prompt("default") == GENERATION_PROMPTS["default"]
    with pytest.raises(ValueError, match="unknown generation prompt"):
        get_prompt("nope")


def test_deltas() -> None:
    a = {"hallucination_rate": 0.10, "faithfulness_mean": 0.90}
    b = {"hallucination_rate": 0.04, "faithfulness_mean": 0.97}
    d = deltas(a, b)
    assert d["hallucination_rate"] == pytest.approx(-0.06)
    assert d["faithfulness_mean"] == pytest.approx(0.07)


def test_significance_uses_ci_band() -> None:
    # a 0.06 move inside a wide CI (half-width 0.075) is not significant
    assert not is_significant(0.06, [0.0, 0.15], [0.0, 0.15])
    # the same move with tight CIs and a small margin is significant
    assert is_significant(0.06, [0.0, 0.01], [0.0, 0.01], margin=0.02)


def test_render_marks_significant_changes() -> None:
    a = {"hallucination_rate": 0.20, "faithfulness_mean": 0.8}
    b = {"hallucination_rate": 0.02, "faithfulness_mean": 0.99}
    out = render("default", "concise", a, b)
    assert "default" in out and "concise" in out
    assert "*" in out  # at least one significant change marked
