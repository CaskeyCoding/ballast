"""One config-driven assembler for the retriever and the RAG graph (RAG-12).

Strategy choices (hybrid retrieval, query transform, reranking, retry cap) all come from `Settings`,
so the eval matrix can vary them via config without touching code. `ask` and the eval runner both go
through here, so there is a single place that wires the pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ballast.core.config import ModelRegistry, Settings
from ballast.core.embed import Embedder
from ballast.core.llm import LLMClient
from ballast.core.rerank import LLMReranker
from ballast.core.retrieve import RerankingRetriever, RetrieverLike, build_retriever
from ballast.core.store import VectorStore
from ballast.core.trace import Trace
from ballast.rag.graph import build_rag_graph
from ballast.rag.prompts import get_prompt
from ballast.rag.transform import HyDERetriever, MultiQueryRetriever


def assemble_retriever(
    settings: Settings,
    store: VectorStore,
    embedder: Embedder,
    client: LLMClient,
    registry: ModelRegistry,
    *,
    chunks: Sequence[tuple[str, str]] = (),
) -> RetrieverLike:
    """Build the retriever stack from config: base -> query transform -> rerank."""
    retriever: RetrieverLike = build_retriever(settings.retrieval, store, embedder, chunks=chunks)
    if settings.query_transform == "multi_query":
        retriever = MultiQueryRetriever(retriever, client, registry)
    elif settings.query_transform == "hyde":
        retriever = HyDERetriever(store, embedder, client, registry)
    if settings.rerank:
        retriever = RerankingRetriever(retriever, LLMReranker(client, registry))
    return retriever


def build_pipeline(
    settings: Settings,
    client: LLMClient,
    registry: ModelRegistry,
    trace: Trace,
    *,
    store: VectorStore,
    embedder: Embedder,
    chunks: Sequence[tuple[str, str]] = (),
) -> Any:
    """Assemble the configured retriever and compile the self-healing graph around it."""
    retriever = assemble_retriever(settings, store, embedder, client, registry, chunks=chunks)
    return build_rag_graph(
        retriever,
        client,
        registry,
        trace,
        max_retries=settings.max_retries,
        system_prompt=get_prompt(settings.generation_prompt),
    )
