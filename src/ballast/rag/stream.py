"""Node-event streaming over a compiled LangGraph graph (RAG-9).

LangGraph's `stream` yields a state update per node as it completes; `iter_node_events` turns that
into a stream of node names so the ask path (and any UI) can show the pipeline executing live.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ballast.rag.state import RAGState


def iter_node_events(graph: Any, state: RAGState) -> Iterator[str]:
    """Yield each node name as it finishes executing in the graph."""
    for event in graph.stream(state):
        yield from event
