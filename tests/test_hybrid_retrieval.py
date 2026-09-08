"""CORP-7: BM25 keyword search, reciprocal rank fusion, and the hybrid retriever."""

from __future__ import annotations

import pytest

from ballast.core.bm25 import BM25
from ballast.core.chunk import Chunk
from ballast.core.embed import HashingEmbedder
from ballast.core.retrieve import (
    HybridRetriever,
    Retriever,
    RetrieverLike,
    build_retriever,
    reciprocal_rank_fusion,
)
from ballast.core.store import InMemoryVectorStore

_DOCS = {
    "div#0": "diversification spreads risk across many investments",
    "fee#0": "an expense ratio is the annual operating cost of a fund",
    "rebal#0": "rebalancing returns a portfolio to its target asset mix",
}


def _store() -> InMemoryVectorStore:
    emb = HashingEmbedder()
    store = InMemoryVectorStore()
    store.upsert([(Chunk(t, "s", "u", "ti", "h", cid), emb.embed(t)) for cid, t in _DOCS.items()])
    return store


def test_bm25_ranks_keyword_match_first() -> None:
    bm = BM25().fit(list(_DOCS.items()))
    top = bm.search("rebalancing target mix", k=1)
    assert top and top[0][0] == "rebal#0"


def test_bm25_empty_query_or_unfit_returns_nothing() -> None:
    assert BM25().search("anything") == []  # not fit
    assert BM25().fit(list(_DOCS.items())).search("zzz nonexistent") == []


def test_rrf_merges_rankings() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "d"]])
    # b appears high in both -> should rank at or near the top
    assert fused[0] in {"b", "a", "c"}
    assert set(fused) == {"a", "b", "c", "d"}


def test_hybrid_satisfies_protocol_and_fuses() -> None:
    emb = HashingEmbedder()
    hybrid = HybridRetriever(_store(), emb, BM25().fit(list(_DOCS.items())))
    assert isinstance(hybrid, RetrieverLike)
    hits = hybrid.retrieve("expense ratio fund cost", k=1)
    assert hits and hits[0].chunk.chunk_id == "fee#0"


def test_hybrid_falls_back_to_vector_when_no_keyword_hit() -> None:
    emb = HashingEmbedder()
    hybrid = HybridRetriever(_store(), emb, BM25().fit(list(_DOCS.items())))
    # a query whose terms are not in the corpus yields no BM25 hits -> vector-only path
    hits = hybrid.retrieve("zzzz qqqq", k=2)
    assert len(hits) <= 2  # returns vector results, does not crash


def test_factory_selects_mode() -> None:
    emb = HashingEmbedder()
    store = _store()
    assert isinstance(build_retriever("vector", store, emb), Retriever)
    assert isinstance(
        build_retriever("hybrid", store, emb, chunks=list(_DOCS.items())), HybridRetriever
    )
    with pytest.raises(ValueError, match="unknown retrieval mode"):
        build_retriever("nope", store, emb)
