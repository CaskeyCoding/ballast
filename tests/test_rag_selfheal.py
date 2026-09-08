"""RAG-3/4/5/6: critic, document grading, the re-retrieve loop, the retry cap and graceful decline.

Calls happen in a known order, so a scripted FakeLLMClient drives each path deterministically:
grade_documents -> generate -> critic, with rewrite_query inserted on a self-heal.
"""

from __future__ import annotations

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_rag_graph
from ballast.rag.nodes import INSUFFICIENT


def _retriever() -> Retriever:
    emb = HashingEmbedder()
    return Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)


def _run(script: list[str], *, max_retries: int = 2) -> tuple[dict, Trace]:
    trace = Trace(run_id="t")
    graph = build_rag_graph(
        _retriever(), FakeLLMClient(script), ModelRegistry(), trace, k=3, max_retries=max_retries
    )
    result = graph.invoke({"question": "what is dollar cost averaging", "retries": 0})
    return result, trace


def test_grounded_first_try_ends() -> None:
    result, trace = _run(
        [
            '{"relevant_indices": [0, 1]}',  # grade
            "Dollar-cost averaging is investing a fixed amount regularly [1].",  # generate
            '{"grounded": true, "relevant": true, "reason": "ok"}',  # critic passes
        ]
    )
    assert result["answer"].startswith("Dollar-cost averaging")
    names = [n.name for n in trace.nodes]
    assert names == ["retrieve", "grade_documents", "generate", "critic"]
    assert result["answer"] != INSUFFICIENT


def test_self_heal_loops_then_succeeds() -> None:
    result, trace = _run(
        [
            '{"relevant_indices": [0]}',  # grade 1
            "first, possibly wrong answer",  # generate 1
            '{"grounded": false, "relevant": true, "reason": "not supported"}',  # critic 1 -> fail
            "what is dollar cost averaging benefit",  # rewrite_query
            '{"relevant_indices": [0]}',  # grade 2
            "second, grounded answer [1]",  # generate 2
            '{"grounded": true, "relevant": true, "reason": "now supported"}',  # critic 2 -> pass
        ]
    )
    assert result["answer"] == "second, grounded answer [1]"
    names = [n.name for n in trace.nodes]
    assert names.count("retrieve") == 2  # the graph looped back and re-retrieved
    assert "rewrite_query" in names


def test_grounded_but_irrelevant_triggers_self_heal() -> None:
    # RAG-8: an answer can be grounded yet evasive; relevancy must also gate the loop.
    result, trace = _run(
        [
            '{"relevant_indices": [0]}',  # grade 1
            "a grounded but off-topic answer",  # generate 1
            '{"grounded": true, "relevant": false, "reason": "evasive"}',  # critic 1 -> fail
            "sharper question",  # rewrite_query
            '{"relevant_indices": [0]}',  # grade 2
            "a grounded and on-topic answer [1]",  # generate 2
            '{"grounded": true, "relevant": true, "reason": "ok"}',  # critic 2 -> pass
        ]
    )
    assert result["answer"] == "a grounded and on-topic answer [1]"
    assert "rewrite_query" in [n.name for n in trace.nodes]


def test_retry_cap_then_graceful_decline() -> None:
    # critic always fails; with max_retries=1 the loop must stop and decline, not spin forever.
    result, trace = _run(
        [
            '{"relevant_indices": [0]}',
            "answer attempt 1",
            '{"grounded": false, "relevant": true, "reason": "no"}',  # critic fail -> rewrite
            "rewritten",
            '{"relevant_indices": [0]}',
            "answer attempt 2",
            '{"grounded": false, "relevant": true, "reason": "x"}',  # critic fail -> fallback
        ],
        max_retries=1,
    )
    assert result["answer"] == INSUFFICIENT
    assert "fallback" in [n.name for n in trace.nodes]


def test_no_relevant_docs_routes_to_rewrite_not_generate() -> None:
    result, trace = _run(
        [
            '{"relevant_indices": []}',  # grade 1: nothing relevant -> rewrite
            "rewritten question",  # rewrite_query
            '{"relevant_indices": [0]}',  # grade 2: relevant -> generate
            "grounded answer [1]",  # generate
            '{"grounded": true, "relevant": true, "reason": "ok"}',  # critic pass
        ]
    )
    names = [n.name for n in trace.nodes]
    # generate only ran after a rewrite triggered by empty grading
    assert names.index("rewrite_query") < names.index("generate")
    assert result["answer"] == "grounded answer [1]"
