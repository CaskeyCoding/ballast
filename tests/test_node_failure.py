"""RAG-15: a failed node call degrades to the graceful fallback, never a silent zero."""

from __future__ import annotations

from collections.abc import Sequence

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.llm import LLMError, LLMResponse, Message
from ballast.core.retrieve import Retriever
from ballast.core.store import Retrieved
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_rag_graph
from ballast.rag.nodes import INSUFFICIENT


class _RaisingClient:
    """An LLMClient whose calls always fail (simulates an API outage)."""

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise LLMError("simulated outage")


class _RaisingRetriever:
    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        raise RuntimeError("store down")


def test_llm_failure_routes_to_fallback() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    trace = Trace("t")
    graph = build_rag_graph(retriever, _RaisingClient(), ModelRegistry(), trace)
    result = graph.invoke({"question": "what is diversification", "retries": 0})
    assert result["answer"] == INSUFFICIENT  # graceful decline, not a crash or empty answer
    assert any(d.kind == "node_error" for d in trace.decisions)
    assert "fallback" in [n.name for n in trace.nodes]


def test_retriever_failure_routes_to_fallback() -> None:
    trace = Trace("t")
    graph = build_rag_graph(_RaisingRetriever(), FakeLLMClient([]), ModelRegistry(), trace)
    result = graph.invoke({"question": "anything", "retries": 0})
    assert result["answer"] == INSUFFICIENT
    assert any(d.kind == "node_error" and d.outcome == "retrieve" for d in trace.decisions)


class _GradeThenFailClient:
    """Grades documents as irrelevant, then fails the rewrite call (partial outage)."""

    def __init__(self) -> None:
        self._calls = 0

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:  # grade_documents: nothing relevant, so the graph goes to rewrite
            return LLMResponse(
                text='{"relevant_indices": []}',
                model=model,
                input_tokens=1,
                output_tokens=1,
                stop_reason="end_turn",
            )
        raise LLMError("simulated outage")


def test_rewrite_failure_routes_to_fallback() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    trace = Trace("t")
    graph = build_rag_graph(retriever, _GradeThenFailClient(), ModelRegistry(), trace)
    question = "what is diversification"
    result = graph.invoke({"question": question, "retries": 0})
    assert result["answer"] == INSUFFICIENT  # graceful decline, not a crash
    assert result["question"] == question  # the original question is kept on rewrite failure
    assert any(d.kind == "node_error" and d.outcome == "rewrite_query" for d in trace.decisions)
    assert "fallback" in [n.name for n in trace.nodes]
