"""Retrieval: embed a query and pull the most similar chunks from the store, with citations.

This is the seam the RAG graph's retrieve node sits on. Each `Retrieved` item carries the full
chunk (source, url, heading_path, chunk_id), so the generate node can cite exactly what it used.
`HybridRetriever` fuses vector and BM25 rankings via reciprocal rank fusion (CORP-7); both satisfy
the `RetrieverLike` protocol so the graph does not care which is wired in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ballast.core.bm25 import BM25
from ballast.core.embed import Embedder
from ballast.core.rerank import Reranker
from ballast.core.store import Retrieved, VectorStore


@runtime_checkable
class RetrieverLike(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]: ...


def source_stem(chunk_id: str) -> str:
    """The corpus doc a chunk belongs to (chunk_id is '<stem>#<index>')."""
    return chunk_id.split("#")[0]


def filter_by_source(results: list[Retrieved], sources: set[str] | None, k: int) -> list[Retrieved]:
    """Metadata filter (CORP-9): keep only chunks from the allowed source stems, then top-k."""
    if sources is None:
        return results[:k]
    return [r for r in results if source_stem(r.chunk.chunk_id) in sources][:k]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], *, c: int = 60) -> list[str]:
    """Fuse several ranked id lists into one. RRF score = sum 1/(c + rank), higher is better."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            score[item] = score.get(item, 0.0) + 1.0 / (c + rank + 1)
    return sorted(score, key=lambda i: -score[i])


@dataclass
class Retriever:
    store: VectorStore
    embedder: Embedder

    def retrieve(
        self, query: str, k: int = 4, *, sources: set[str] | None = None
    ) -> list[Retrieved]:
        pool = k if sources is None else max(k * 5, 20)
        results = self.store.search(self.embedder.embed(query), k=pool)
        return filter_by_source(results, sources, k)


@dataclass
class HybridRetriever:
    """Fuse vector similarity and BM25 keyword rankings via RRF; fall back to vector-only."""

    store: VectorStore
    embedder: Embedder
    bm25: BM25
    rrf_c: int = 60
    pool: int = 10

    def retrieve(
        self, query: str, k: int = 4, *, sources: set[str] | None = None
    ) -> list[Retrieved]:
        vec = self.store.search(self.embedder.embed(query), k=self.pool)
        bm = self.bm25.search(query, k=self.pool)
        if not bm:  # no keyword signal: vector-only
            return filter_by_source(vec, sources, k)
        vec_by_id = {r.chunk.chunk_id: r for r in vec}
        fused = reciprocal_rank_fusion(
            [[r.chunk.chunk_id for r in vec], [cid for cid, _ in bm]], c=self.rrf_c
        )
        out: list[Retrieved] = []
        for rank, cid in enumerate(fused):
            chunk = vec_by_id[cid].chunk if cid in vec_by_id else self.store.get(cid)
            if chunk is not None:
                out.append(Retrieved(chunk=chunk, score=1.0 / (rank + 1)))
        return filter_by_source(out, sources, k)


@dataclass
class RerankingRetriever:
    """Wrap any retriever: pull a larger pool, then rerank down to k (CORP-8)."""

    base: RetrieverLike
    reranker: Reranker
    pool: int = 10

    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        candidates = self.base.retrieve(query, k=self.pool)
        return self.reranker.rerank(query, candidates, k)


def build_retriever(
    mode: str,
    store: VectorStore,
    embedder: Embedder,
    *,
    chunks: Sequence[tuple[str, str]] = (),
) -> RetrieverLike:
    """Factory: 'vector' (default) or 'hybrid' (needs (chunk_id, text) pairs to fit BM25)."""
    if mode == "vector":
        return Retriever(store=store, embedder=embedder)
    if mode == "hybrid":
        return HybridRetriever(store=store, embedder=embedder, bm25=BM25().fit(list(chunks)))
    raise ValueError(f"unknown retrieval mode {mode!r}; use 'vector' or 'hybrid'")
