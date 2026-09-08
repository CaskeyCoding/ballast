"""Refusal correctness: did the pipeline decline when it should, and answer when it should?

Both error directions matter. A system that always refuses scores perfectly on hallucination but is
useless (over-refusal); one that always answers hallucinates on the unanswerable cases (under).
"""

from __future__ import annotations

from dataclasses import dataclass

from ballast.gateway.fallback import INSUFFICIENT

# Substrings marking a decline: the RAG insufficient-info reply and the gateway safe fallbacks.
_DECLINE_MARKERS = (
    INSUFFICIENT,
    "could not be processed",
    "withheld by a safety guardrail",
)


def is_refusal(text: str) -> bool:
    return any(marker in text for marker in _DECLINE_MARKERS)


@dataclass
class RefusalStats:
    correct: int
    over_refused: int  # should have answered, but declined
    under_refused: int  # should have declined, but answered
    total: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def refusal_stats(items: list[tuple[bool, bool]]) -> RefusalStats:
    """items: list of (should_decline, did_refuse)."""
    correct = over = under = 0
    for should_decline, did_refuse in items:
        if should_decline == did_refuse:
            correct += 1
        elif should_decline and not did_refuse:
            under += 1
        else:
            over += 1
    return RefusalStats(correct=correct, over_refused=over, under_refused=under, total=len(items))
