"""Query transformation strategies that feed retrieval (RAG-7), both off by default.

multi_query fans out reformulations of the question, retrieves each, and unions the results, which
lifts recall when one phrasing under-retrieves. HyDE generates a hypothetical answer and embeds that
instead of the bare question, since an answer often sits closer to the source passages in vector
space. Both satisfy the `RetrieverLike` protocol, so the graph does not know which is wired in.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.embed import Embedder
from ballast.core.llm import LLMClient
from ballast.core.retrieve import RetrieverLike
from ballast.core.store import Retrieved, VectorStore
from ballast.core.structured import complete_structured


class _Reformulations(BaseModel):
    queries: list[str]


@dataclass
class MultiQueryRetriever:
    base: RetrieverLike
    client: LLMClient
    registry: ModelRegistry
    n: int = 3

    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        reforms = complete_structured(
            self.client,
            [{"role": "user", "content": f"Question: {query}"}],
            _Reformulations,
            model=self.registry.resolve("generation"),
            system=(
                f"Produce {self.n} alternative phrasings of the question that would retrieve "
                'relevant material. Return JSON {"queries": [..]}.'
            ),
        )
        best: dict[str, Retrieved] = {}
        for q in [query, *reforms.queries[: self.n]]:
            for r in self.base.retrieve(q, k=k):
                cur = best.get(r.chunk.chunk_id)
                if cur is None or r.score > cur.score:
                    best[r.chunk.chunk_id] = r
        return sorted(best.values(), key=lambda r: -r.score)[:k]


@dataclass
class HyDERetriever:
    store: VectorStore
    embedder: Embedder
    client: LLMClient
    registry: ModelRegistry

    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        resp = self.client.complete(
            [{"role": "user", "content": f"Write a short, plausible answer to: {query}"}],
            model=self.registry.resolve("generation"),
        )
        return self.store.search(self.embedder.embed(resp.text), k=k)
