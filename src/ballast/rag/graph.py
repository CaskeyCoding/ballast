"""Assemble the self-healing RAG graph.

Flow:

    START -> retrieve -> grade_documents -> (generate | rewrite_query | fallback)
    generate -> critic -> (END if grounded | rewrite_query if retries left | fallback)
    rewrite_query -> retrieve   (the cycle; fallback if the rewrite call itself fails)
    fallback -> END

The conditional edges plus the `retries` counter make this stateful and cyclical rather than a
linear chain: the graph critiques its own answer and either re-retrieves with a rewritten query or
declines gracefully. `build_baseline_graph` keeps the simple retrieve -> generate path for RAG-1.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.retrieve import RetrieverLike
from ballast.core.trace import Trace
from ballast.rag.nodes import (
    GENERATE_SYSTEM,
    critic_node,
    fallback_node,
    generate_node,
    grade_documents_node,
    retrieve_node,
    rewrite_query_node,
)
from ballast.rag.state import RAGState


def _route_after_grade(state: RAGState, *, max_retries: int) -> str:
    if state.get("failed"):  # a node call failed (RAG-15): decline, do not build on a zero
        return "fallback"
    if state.get("documents"):
        return "generate"
    return "rewrite_query" if state.get("retries", 0) < max_retries else "fallback"


def _route_after_generate(state: RAGState) -> str:
    return "fallback" if state.get("failed") else "critic"


def _route_after_rewrite(state: RAGState) -> str:
    # A failed rewrite call (RAG-15) declines with the original question rather than re-retrieving.
    return "fallback" if state.get("failed") else "retrieve"


def _route_after_critic(state: RAGState, *, max_retries: int) -> str:
    if state.get("failed"):  # critic call failed (RAG-15): decline rather than guess
        return "fallback"
    # End only when the answer is both grounded and relevant (RAG-8); else self-heal or decline.
    if state.get("grounded") and state.get("relevant"):
        return "end"
    return "rewrite_query" if state.get("retries", 0) < max_retries else "fallback"


def build_baseline_graph(
    retriever: RetrieverLike,
    client: LLMClient,
    registry: ModelRegistry,
    trace: Trace,
    *,
    k: int = 4,
    system_prompt: str = GENERATE_SYSTEM,
) -> Any:
    """RAG-1 baseline: retrieve -> generate -> END (no self-heal)."""
    builder = StateGraph(RAGState)
    builder.add_node("retrieve", partial(retrieve_node, retriever=retriever, k=k, trace=trace))
    builder.add_node(
        "generate",
        partial(
            generate_node,
            client=client,
            registry=registry,
            trace=trace,
            system_prompt=system_prompt,
        ),
    )
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()


def build_rag_graph(
    retriever: RetrieverLike,
    client: LLMClient,
    registry: ModelRegistry,
    trace: Trace,
    *,
    k: int = 4,
    max_retries: int = 2,
    checkpointer: Any = None,
    system_prompt: str = GENERATE_SYSTEM,
) -> Any:
    """The self-healing graph: grade documents, generate, critique, re-retrieve or decline.

    Pass a LangGraph checkpointer to persist state by thread id (RAG-11), so a follow-up question
    invoked with the same thread_id reuses the prior conversation history.
    """
    g = StateGraph(RAGState)
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever, k=k, trace=trace))
    g.add_node(
        "grade_documents",
        partial(grade_documents_node, client=client, registry=registry, trace=trace),
    )
    g.add_node(
        "generate",
        partial(
            generate_node,
            client=client,
            registry=registry,
            trace=trace,
            system_prompt=system_prompt,
        ),
    )
    g.add_node("critic", partial(critic_node, client=client, registry=registry, trace=trace))
    g.add_node(
        "rewrite_query",
        partial(rewrite_query_node, client=client, registry=registry, trace=trace),
    )
    g.add_node("fallback", partial(fallback_node, trace=trace))

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_conditional_edges(
        "grade_documents",
        partial(_route_after_grade, max_retries=max_retries),
        {"generate": "generate", "rewrite_query": "rewrite_query", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"critic": "critic", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "critic",
        partial(_route_after_critic, max_retries=max_retries),
        {"end": END, "rewrite_query": "rewrite_query", "fallback": "fallback"},
    )
    g.add_conditional_edges(
        "rewrite_query",
        _route_after_rewrite,
        {"retrieve": "retrieve", "fallback": "fallback"},
    )
    g.add_edge("fallback", END)
    return g.compile(checkpointer=checkpointer)
