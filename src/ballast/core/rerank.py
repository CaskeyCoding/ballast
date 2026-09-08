"""Reranking: reorder retrieval candidates by relevance (CORP-8).

First-stage retrieval ranking (vector or hybrid) is coarse; a reranker is the cheapest large quality
lever. This uses a single structured LLM call to order the candidate indices, so it is one call per
query regardless of pool size. A cross-encoder could slot in behind the same `Reranker` protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.store import Retrieved
from ballast.core.structured import complete_structured


class _Ranking(BaseModel):
    order: list[int]


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[Retrieved], top_k: int
    ) -> list[Retrieved]: ...


class LLMReranker:
    """Order candidates with one structured judge call; out-of-range/missing indices are healed."""

    def __init__(self, client: LLMClient, registry: ModelRegistry) -> None:
        self._client = client
        self._registry = registry

    def rerank(self, query: str, candidates: Sequence[Retrieved], top_k: int) -> list[Retrieved]:
        cands = list(candidates)
        if len(cands) <= 1:
            return cands[:top_k]
        listing = "\n\n".join(f"[{i}] {c.chunk.text}" for i, c in enumerate(cands))
        ranking = complete_structured(
            self._client,
            [{"role": "user", "content": f"Question: {query}\n\nCandidates:\n{listing}"}],
            _Ranking,
            model=self._registry.resolve("judge"),
            system=(
                "Order the candidate indices from most to least relevant to the question. Return "
                'JSON {"order": [..]} listing each candidate index exactly once.'
            ),
        )
        seen: set[int] = set()
        ordered: list[Retrieved] = []
        for i in ranking.order:
            if 0 <= i < len(cands) and i not in seen:
                ordered.append(cands[i])
                seen.add(i)
        for j, c in enumerate(cands):  # append anything the model dropped, preserving order
            if j not in seen:
                ordered.append(c)
        return ordered[:top_k]
