"""Async execution of the RAG graph (RAG-10).

LangGraph compiled graphs expose `ainvoke`; sync nodes run in a threadpool, so the I/O-bound LLM and
store calls do not block the event loop. This wrapper is the documented async entry point and lets a
caller run several questions concurrently.
"""

from __future__ import annotations

from typing import Any

from ballast.rag.state import RAGState


async def ainvoke(graph: Any, state: RAGState) -> RAGState:
    """Run the compiled graph asynchronously and return the final state."""
    result: RAGState = await graph.ainvoke(state)
    return result
