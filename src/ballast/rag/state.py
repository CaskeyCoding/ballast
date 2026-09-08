"""The graph state threaded through the RAG pipeline.

`total=False` so nodes can return partial updates. `retries` exists from the start because the
self-heal loop (RAG-3..6) increments it; the baseline graph just leaves it at zero.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ballast.core.store import Retrieved


class Turn(TypedDict):
    question: str
    answer: str


class Citation(TypedDict):
    title: str
    source: str
    url: str
    chunk_id: str


class RAGState(TypedDict, total=False):
    question: str
    documents: list[Retrieved]
    answer: str
    citations: list[Citation]
    critique: str
    grounded: bool
    relevant: bool
    failed: bool  # a node's LLM/store call failed; route to fallback, never emit a silent zero
    correction: str  # a gateway auto-retry correction instruction for generation (GW-12)
    history: Annotated[list[Turn], operator.add]  # prior turns, persisted by thread (RAG-11)
    retries: int
