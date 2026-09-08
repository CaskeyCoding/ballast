"""Hallucination rate: the headline number the merge gate keys on.

A hallucination is the system asserting something it should not: either an unfaithful substantive
answer, or answering a question it should have declined. Computed over per-case outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CaseOutcome:
    should_decline: bool
    refused: bool
    faithfulness: float | None  # None when the system refused (no claims to judge)


def is_hallucination(case: CaseOutcome) -> bool:
    if case.should_decline:
        return not case.refused  # answered when it should have declined
    if case.refused:
        return False  # declining an answerable question is over-refusal, a different error
    return case.faithfulness == 0.0  # answered but unsupported


def hallucination_rate(cases: list[CaseOutcome]) -> float:
    if not cases:
        return 0.0
    return sum(1 for c in cases if is_hallucination(c)) / len(cases)
