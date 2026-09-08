"""CORP-8: the LLM reranker reorders candidates and the RerankingRetriever wraps a base."""

from __future__ import annotations

from ballast.core.chunk import Chunk
from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.rerank import LLMReranker, Reranker
from ballast.core.retrieve import RerankingRetriever, Retriever
from ballast.core.store import InMemoryVectorStore, Retrieved
from ballast.core.testing import FakeLLMClient


def _cand(cid: str) -> Retrieved:
    return Retrieved(chunk=Chunk(cid, "s", "u", "t", "h", cid), score=0.0)


def test_reranker_reorders_by_model_order() -> None:
    reranker = LLMReranker(FakeLLMClient(['{"order": [2, 0, 1]}']), ModelRegistry())
    out = reranker.rerank("q", [_cand("a"), _cand("b"), _cand("c")], top_k=3)
    assert [r.chunk.chunk_id for r in out] == ["c", "a", "b"]


def test_reranker_heals_missing_and_out_of_range() -> None:
    # model returns a bad index (9) and drops index 2; result must still cover all candidates
    reranker = LLMReranker(FakeLLMClient(['{"order": [9, 1]}']), ModelRegistry())
    out = reranker.rerank("q", [_cand("a"), _cand("b"), _cand("c")], top_k=3)
    ids = [r.chunk.chunk_id for r in out]
    assert ids[0] == "b"  # the one valid ranked index first
    assert set(ids) == {"a", "b", "c"}  # dropped ones appended


def test_single_candidate_skips_model() -> None:
    client = FakeLLMClient([])  # would raise if called
    out = LLMReranker(client, ModelRegistry()).rerank("q", [_cand("a")], top_k=4)
    assert [r.chunk.chunk_id for r in out] == ["a"]
    assert client.calls == []


def test_reranking_retriever_wraps_base() -> None:
    emb = HashingEmbedder()
    store = InMemoryVectorStore()
    store.upsert(
        [
            (Chunk(t, "s", "u", "t", "h", cid), emb.embed(t))
            for cid, t in {"x#0": "alpha", "y#0": "beta"}.items()
        ]
    )
    base = Retriever(store, emb)
    reranker = LLMReranker(FakeLLMClient(['{"order": [1, 0]}']), ModelRegistry())
    wrapped = RerankingRetriever(base, reranker, pool=10)
    assert isinstance(reranker, Reranker)
    out = wrapped.retrieve("alpha beta", k=2)
    assert len(out) == 2  # pulled the pool and reranked to k
