"""RAG-10: the graph runs under async invocation, including the self-heal loop."""

from __future__ import annotations

import asyncio

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.aexec import ainvoke
from ballast.rag.graph import build_rag_graph


def _retriever() -> Retriever:
    emb = HashingEmbedder()
    return Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)


def test_async_invoke_grounded_first_try() -> None:
    client = FakeLLMClient(
        [
            '{"relevant_indices": [0]}',
            "an async answer [1]",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
        ]
    )
    graph = build_rag_graph(_retriever(), client, ModelRegistry(), Trace("t"))
    result = asyncio.run(ainvoke(graph, {"question": "what is diversification", "retries": 0}))
    assert result["answer"] == "an async answer [1]"


def test_async_self_heal_loop() -> None:
    client = FakeLLMClient(
        [
            '{"relevant_indices": [0]}',
            "first answer",
            '{"grounded": false, "relevant": true, "reason": "no"}',
            "rewritten",
            '{"relevant_indices": [0]}',
            "healed answer [1]",
            '{"grounded": true, "relevant": true, "reason": "ok"}',
        ]
    )
    trace = Trace("t")
    graph = build_rag_graph(_retriever(), client, ModelRegistry(), trace)
    result = asyncio.run(ainvoke(graph, {"question": "what is diversification", "retries": 0}))
    assert result["answer"] == "healed answer [1]"
    assert [n.name for n in trace.nodes].count("retrieve") == 2  # looped under async
