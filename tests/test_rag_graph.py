"""RAG-1 + RAG-2: the baseline graph retrieves, generates, and cites real corpus chunks."""

from __future__ import annotations

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_baseline_graph


def _retriever() -> Retriever:
    emb = HashingEmbedder()
    return Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)


def test_baseline_graph_answers_with_citations() -> None:
    trace = Trace(run_id="t")
    client = FakeLLMClient(["Dollar-cost averaging means investing a fixed amount regularly [1]."])
    graph = build_baseline_graph(_retriever(), client, ModelRegistry(), trace, k=3)

    result = graph.invoke({"question": "what is dollar cost averaging", "retries": 0})

    assert result["answer"].startswith("Dollar-cost averaging")
    assert result["citations"], "must cite the sources it was given"
    sources = {c["chunk_id"].split("#")[0] for c in result["citations"]}
    assert "dollar-cost-averaging" in sources
    # both nodes ran and were traced
    assert [n.name for n in trace.nodes] == ["retrieve", "generate"]


def test_generate_receives_retrieved_context() -> None:
    trace = Trace(run_id="t")
    client = FakeLLMClient(["ok [1]"])
    graph = build_baseline_graph(_retriever(), client, ModelRegistry(), trace, k=2)
    graph.invoke({"question": "how do index funds work", "retries": 0})
    # the prompt the model saw must contain retrieved source text
    sent = client.calls[0]["messages"][0]["content"]
    assert "Sources:" in sent and "index" in sent.lower()
