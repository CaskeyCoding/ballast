"""RAG node implementations and the prompt that keeps generation grounded.

Nodes are plain functions of the state; dependencies (retriever, client, registry, trace) are bound
in graph.py. The generate node is instructed to answer only from the provided sources and to decline
when they do not support an answer, which is what makes the critic and self-heal loop meaningful.
"""

from __future__ import annotations

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.retrieve import RetrieverLike
from ballast.core.store import Retrieved
from ballast.core.structured import complete_structured
from ballast.core.trace import Trace
from ballast.rag.prompts import GENERATION_PROMPTS
from ballast.rag.state import Citation, RAGState, Turn

INSUFFICIENT = "I do not have enough information to answer that from the available material."


class DocGrades(BaseModel):
    relevant_indices: list[int]


class Critique(BaseModel):
    grounded: bool
    relevant: bool  # does the answer actually address the question (distinct from groundedness)
    reason: str


GENERATE_SYSTEM = GENERATION_PROMPTS["default"]


def format_context(documents: list[Retrieved]) -> str:
    blocks = []
    for i, r in enumerate(documents, start=1):
        c = r.chunk
        blocks.append(f"[{i}] ({c.title} - {c.heading_path})\n{c.text}")
    return "\n\n".join(blocks) if blocks else "(no sources retrieved)"


def citations_from(documents: list[Retrieved]) -> list[Citation]:
    return [
        Citation(
            title=r.chunk.title, source=r.chunk.source, url=r.chunk.url, chunk_id=r.chunk.chunk_id
        )
        for r in documents
    ]


def _node_failure(trace: Trace, node: str, exc: Exception) -> RAGState:
    # Tri-state: a failed external call records the failure and routes to fallback (Lesson 1),
    # never a silent empty/zero result that downstream nodes would treat as real.
    trace.record_node(node, "FAILED")
    trace.record_decision("node_error", node, str(exc))
    return {"failed": True}


def retrieve_node(state: RAGState, *, retriever: RetrieverLike, k: int, trace: Trace) -> RAGState:
    try:
        docs = retriever.retrieve(state["question"], k=k)
    except Exception as exc:  # noqa: BLE001 - any retrieval failure degrades to fallback
        return _node_failure(trace, "retrieve", exc)
    trace.record_node("retrieve", f"{len(docs)} chunks")
    return {"documents": docs}


def generate_node(
    state: RAGState,
    *,
    client: LLMClient,
    registry: ModelRegistry,
    trace: Trace,
    system_prompt: str = GENERATE_SYSTEM,
) -> RAGState:
    documents = state.get("documents", [])
    context = format_context(documents)
    correction = state.get("correction", "")
    extra = f"\n\nIMPORTANT: {correction}" if correction else ""
    history = state.get("history", [])
    prior = "".join(f"\nEarlier Q: {t['question']}\nEarlier A: {t['answer']}" for t in history)
    convo = f"\n\nConversation so far:{prior}" if prior else ""
    messages = [
        {
            "role": "user",
            "content": f"Sources:\n{context}{convo}\n\nQuestion: {state['question']}{extra}",
        }
    ]
    try:
        resp = client.complete(messages, model=registry.resolve("generation"), system=system_prompt)
    except Exception as exc:  # noqa: BLE001 - degrade to fallback rather than crash the graph
        return _node_failure(trace, "generate", exc)
    trace.record_node("generate", f"{resp.output_tokens} out tokens")
    return {"answer": resp.text.strip(), "citations": citations_from(documents)}


def grade_documents_node(
    state: RAGState, *, client: LLMClient, registry: ModelRegistry, trace: Trace
) -> RAGState:
    """CRAG-style: keep only the retrieved chunks relevant to the question."""
    documents = state.get("documents", [])
    if not documents:
        return {"documents": []}
    listing = "\n\n".join(f"[{i}] {r.chunk.text}" for i, r in enumerate(documents))
    try:
        grades = complete_structured(
            client,
            [{"role": "user", "content": f"Question: {state['question']}\n\nChunks:\n{listing}"}],
            DocGrades,
            model=registry.resolve("grader"),
            system=(
                "Return the 0-based indices of the chunks relevant to answering the question, "
                'as JSON {"relevant_indices": [..]}. Be strict: drop chunks that are off-topic.'
            ),
        )
    except Exception as exc:  # noqa: BLE001 - degrade to fallback rather than crash
        return _node_failure(trace, "grade_documents", exc)
    keep = [documents[i] for i in grades.relevant_indices if 0 <= i < len(documents)]
    trace.record_node("grade_documents", f"kept {len(keep)}/{len(documents)}")
    trace.record_decision("grade_documents", "kept" if keep else "none_relevant")
    return {"documents": keep}


def critic_node(
    state: RAGState, *, client: LLMClient, registry: ModelRegistry, trace: Trace
) -> RAGState:
    """Decide whether the answer is supported by the cited sources."""
    context = format_context(state.get("documents", []))
    try:
        verdict = complete_structured(
            client,
            [
                {
                    "role": "user",
                    "content": (
                        f"Question: {state['question']}\n\nSources:\n{context}\n\n"
                        f"Answer:\n{state.get('answer', '')}"
                    ),
                }
            ],
            Critique,
            model=registry.resolve("critic"),
            system=(
                "You check the answer on two axes. Return JSON "
                '{"grounded": bool, "relevant": bool, "reason": str}. grounded is false if the '
                "answer asserts anything the sources do not support, or answers when the sources "
                "lack the information. relevant is false if the answer does not address the "
                "question (for example it is evasive or off-topic), even if claims are supported."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - degrade to fallback rather than crash
        return _node_failure(trace, "critic", exc)
    ok = verdict.grounded and verdict.relevant
    trace.record_node("critic", verdict.reason)
    trace.record_decision("critic", "pass" if ok else "fail", verdict.reason)
    update: RAGState = {
        "critique": verdict.reason,
        "grounded": verdict.grounded,
        "relevant": verdict.relevant,
    }
    if ok:  # remember this turn for follow-up questions on the same thread (RAG-11)
        update["history"] = [Turn(question=state["question"], answer=state.get("answer", ""))]
    return update


def rewrite_query_node(
    state: RAGState, *, client: LLMClient, registry: ModelRegistry, trace: Trace
) -> RAGState:
    """Reformulate the question to retrieve better sources, and count the retry."""
    try:
        resp = client.complete(
            [
                {
                    "role": "user",
                    "content": (
                        f"The question '{state['question']}' did not retrieve usable sources. "
                        "Rewrite it to surface better matches. Return only the rewritten question."
                    ),
                }
            ],
            model=registry.resolve("generation"),
        )
    except Exception as exc:  # noqa: BLE001 - degrade to fallback rather than crash
        return _node_failure(trace, "rewrite_query", exc)
    retries = state.get("retries", 0) + 1
    trace.record_node("rewrite_query", f"retry {retries}")
    return {"question": resp.text.strip(), "retries": retries}


def fallback_node(state: RAGState, *, trace: Trace) -> RAGState:
    """Decline gracefully rather than guess once the self-heal budget is exhausted."""
    trace.record_node("fallback", "insufficient information")
    trace.record_decision("fallback", "declined")
    return {
        "answer": INSUFFICIENT,
        "citations": [],
        "history": [Turn(question=state["question"], answer=INSUFFICIENT)],
    }
