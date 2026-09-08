"""RAG-12: one config-driven builder assembles the retriever stack and the graph."""

from __future__ import annotations

from ballast.core.chunk import Chunk
from ballast.core.config import ModelRegistry, Settings
from ballast.core.embed import HashingEmbedder
from ballast.core.retrieve import HybridRetriever, RerankingRetriever, Retriever
from ballast.core.store import InMemoryVectorStore
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.pipeline import assemble_retriever, build_pipeline
from ballast.rag.transform import HyDERetriever, MultiQueryRetriever

_CHUNKS = [("a#0", "diversification spreads risk"), ("b#0", "compound interest grows")]


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def _store() -> InMemoryVectorStore:
    emb = HashingEmbedder()
    store = InMemoryVectorStore()
    store.upsert([(Chunk(t, "s", "u", "t", "h", cid), emb.embed(t)) for cid, t in _CHUNKS])
    return store


def test_default_is_plain_vector_retriever() -> None:
    r = assemble_retriever(
        _settings(), _store(), HashingEmbedder(), FakeLLMClient([]), ModelRegistry(), chunks=_CHUNKS
    )
    assert isinstance(r, Retriever)


def test_flags_select_strategies() -> None:
    emb = HashingEmbedder()
    store = _store()
    fake = FakeLLMClient([])
    reg = ModelRegistry()
    assert isinstance(
        assemble_retriever(_settings(retrieval="hybrid"), store, emb, fake, reg, chunks=_CHUNKS),
        HybridRetriever,
    )
    assert isinstance(
        assemble_retriever(_settings(query_transform="multi_query"), store, emb, fake, reg),
        MultiQueryRetriever,
    )
    assert isinstance(
        assemble_retriever(_settings(query_transform="hyde"), store, emb, fake, reg),
        HyDERetriever,
    )


def test_rerank_wraps_the_transform() -> None:
    r = assemble_retriever(
        _settings(query_transform="hyde", rerank=True),
        _store(),
        HashingEmbedder(),
        FakeLLMClient([]),
        ModelRegistry(),
    )
    assert isinstance(r, RerankingRetriever)
    assert isinstance(r.base, HyDERetriever)  # rerank is outermost, wrapping the transform


def test_build_pipeline_runs_with_configured_max_retries() -> None:
    # a grade -> generate -> critic(pass) flow compiles and runs through the assembled graph
    client = FakeLLMClient(
        [
            '{"relevant_indices": [0]}',
            "an answer [1]",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
        ]
    )
    graph = build_pipeline(
        _settings(max_retries=1),
        client,
        ModelRegistry(),
        Trace("t"),
        store=_store(),
        embedder=HashingEmbedder(),
        chunks=_CHUNKS,
    )
    result = graph.invoke({"question": "what is diversification", "retries": 0})
    assert result["answer"] == "an answer [1]"
