"""EVAL-19: judge calibration agreement against the human-labeled set."""

from __future__ import annotations

from collections.abc import Sequence

from ballast.eval.calibration import LabeledExample, agreement, load_labels


def test_labels_load() -> None:
    labels = load_labels()
    assert len(labels) >= 6
    assert any(ex.faithful for ex in labels) and any(not ex.faithful for ex in labels)


def test_perfect_judge_agrees_fully() -> None:
    labels = [
        LabeledExample(question="q", answer="a", source="s", faithful=True),
        LabeledExample(question="q", answer="b", source="s", faithful=False),
    ]

    def perfect(q: str, a: str, s: Sequence[str]) -> float:
        return 1.0 if a == "a" else 0.0  # matches the labels exactly

    assert agreement(labels, perfect) == 1.0


def test_wrong_judge_lowers_agreement() -> None:
    labels = [
        LabeledExample(question="q", answer="a", source="s", faithful=True),
        LabeledExample(question="q", answer="b", source="s", faithful=False),
    ]

    def always_faithful(q: str, a: str, s: Sequence[str]) -> float:
        return 1.0  # disagrees on the unfaithful example

    assert agreement(labels, always_faithful) == 0.5
