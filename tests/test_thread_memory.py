"""RAG-11: a checkpointer persists state by thread id so a follow-up reuses prior context."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_rag_graph


def _retriever() -> Retriever:
    emb = HashingEmbedder()
    return Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)


def test_history_accumulates_across_thread() -> None:
    # two grounded-first-try turns on the same thread
    client = FakeLLMClient(
        [
            '{"relevant_indices": [0]}',
            "answer one [1]",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
            '{"relevant_indices": [0]}',
            "answer two [1]",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
        ]
    )
    graph = build_rag_graph(
        _retriever(), client, ModelRegistry(), Trace("t"), checkpointer=InMemorySaver()
    )
    cfg = {"configurable": {"thread_id": "T1"}}

    graph.invoke({"question": "what is diversification", "retries": 0}, cfg)
    r2 = graph.invoke({"question": "and how does it reduce risk", "retries": 0}, cfg)

    # the thread accumulated both turns
    assert len(r2["history"]) == 2
    assert r2["history"][0]["answer"] == "answer one [1]"
    # the second generation prompt saw the prior turn (follow-up context)
    second_generate = client.calls[4]["messages"][0]["content"]
    assert "Conversation so far" in second_generate and "answer one" in second_generate


def test_separate_threads_do_not_share_history() -> None:
    client = FakeLLMClient(
        [
            '{"relevant_indices": [0]}',
            "a",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
            '{"relevant_indices": [0]}',
            "b",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
        ]
    )
    graph = build_rag_graph(
        _retriever(), client, ModelRegistry(), Trace("t"), checkpointer=InMemorySaver()
    )
    graph.invoke({"question": "q", "retries": 0}, {"configurable": {"thread_id": "A"}})
    rb = graph.invoke({"question": "q", "retries": 0}, {"configurable": {"thread_id": "B"}})
    assert len(rb["history"]) == 1  # thread B is independent
