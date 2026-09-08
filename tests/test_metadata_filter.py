"""CORP-9: retrieval can be restricted to allowed source stems."""

from __future__ import annotations

from ballast.core.bm25 import BM25
from ballast.core.chunk import Chunk
from ballast.core.embed import HashingEmbedder
from ballast.core.retrieve import (
    HybridRetriever,
    Retriever,
    filter_by_source,
    source_stem,
)
from ballast.core.store import InMemoryVectorStore, Retrieved

_DOCS = {
    "div#0": "diversification spreads risk across many investments",
    "comp#0": "compound interest grows over time",
    "fee#0": "an expense ratio is the annual cost of a fund",
}


def _store() -> InMemoryVectorStore:
    emb = HashingEmbedder()
    store = InMemoryVectorStore()
    store.upsert([(Chunk(t, "s", "u", "ti", "h", cid), emb.embed(t)) for cid, t in _DOCS.items()])
    return store


def test_source_stem_and_filter() -> None:
    assert source_stem("comp#3") == "comp"
    rs = [
        Retrieved(Chunk("x", "s", "u", "t", "h", "comp#0"), 1.0),
        Retrieved(Chunk("y", "s", "u", "t", "h", "div#0"), 0.5),
    ]
    kept = filter_by_source(rs, {"comp"}, k=4)
    assert [r.chunk.chunk_id for r in kept] == ["comp#0"]


def test_retriever_restricts_to_sources() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(_store(), emb)
    hits = retriever.retrieve("interest and risk and fund", k=3, sources={"fee"})
    assert hits and all(source_stem(h.chunk.chunk_id) == "fee" for h in hits)


def test_hybrid_restricts_to_sources() -> None:
    emb = HashingEmbedder()
    hybrid = HybridRetriever(_store(), emb, BM25().fit(list(_DOCS.items())))
    hits = hybrid.retrieve("compound interest fund risk", k=3, sources={"comp"})
    assert hits and all(source_stem(h.chunk.chunk_id) == "comp" for h in hits)
