"""Context precision and recall (EVAL-5): retrieval quality against per-question source labels.

Most answer failures are retrieval failures, so measuring retrieval separately localizes the fault.
Precision = fraction of the surfaced sources that were relevant; recall = fraction of the relevant
sources that were surfaced. Sources are corpus doc stems (the part of a chunk_id before '#').
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class ContextScore:
    precision: float
    recall: float


def context_scores(retrieved: set[str], relevant: set[str]) -> ContextScore:
    if not relevant:
        return ContextScore(1.0, 1.0)  # nothing was expected; trivially satisfied
    hits = len(retrieved & relevant)
    precision = hits / len(retrieved) if retrieved else 0.0
    recall = hits / len(relevant)
    return ContextScore(precision=precision, recall=recall)


def mean_context(scores: Sequence[ContextScore]) -> ContextScore:
    if not scores:
        return ContextScore(1.0, 1.0)
    n = len(scores)
    return ContextScore(
        precision=sum(s.precision for s in scores) / n,
        recall=sum(s.recall for s in scores) / n,
    )


def source_of(chunk_id: str) -> str:
    """The corpus doc stem a chunk belongs to (chunk_id is '<stem>#<index>')."""
    return chunk_id.split("#")[0]
