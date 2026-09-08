"""End-to-end walkthrough (DX-2): one question through ingest, ask, and the trace, narrated.

A runnable tour of the self-healing RAG stack. It indexes the seed corpus, asks a question through
the same pipeline `make ask` uses, and prints the run trace so a reader can see each step: how many
chunks were indexed, the cited answer, and the node-by-node flow with cost and tokens.

Run it for real (uses the key from Secrets Manager):
    python examples/walkthrough.py
    python examples/walkthrough.py "how should I think about diversification"

The pipeline takes an injected `LLMClient`, so a test drives the same flow with a FakeLLMClient and
no API key (see tests/test_walkthrough.py).
"""

from __future__ import annotations

import argparse
import sys

from ballast.core.config import ModelRegistry, Settings
from ballast.core.cost import CostMeter
from ballast.core.embed import get_embedder
from ballast.core.ingest import CORPUS_DIR, build_index, chunk_corpus
from ballast.core.llm import LLMClient
from ballast.core.store import get_store
from ballast.core.trace import MeteredClient, Trace
from ballast.obs.viewer import render_trace
from ballast.rag.pipeline import build_pipeline

DEFAULT_QUESTION = "What is diversification and why does it matter?"


def run_walkthrough(
    question: str = DEFAULT_QUESTION,
    *,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> Trace:
    """Index the corpus, ask the question, and print the narrated end-to-end flow."""
    settings = settings or Settings()
    trace = Trace(run_id="walkthrough")

    if client is None:  # real run: the key is resolved from Secrets Manager, never read from disk
        from ballast.core.llm import ClaudeClient

        client = ClaudeClient(settings.resolve_api_key())
    metered = MeteredClient(client, CostMeter(settings.run_budget_usd), trace)

    print("=" * 70)
    print(f"Q: {question}")
    print("=" * 70)

    # Step 1: ingest. Chunk the corpus and build the in-memory index the retriever searches.
    embedder = get_embedder(settings.embedder, model_name=settings.embed_model)
    store = get_store(settings.vector_store, chroma_dir=settings.chroma_dir)
    build_index(CORPUS_DIR, embedder, store=store)
    pairs = [(c.chunk_id, c.text) for c in chunk_corpus(CORPUS_DIR)]
    print(f"\n[1/3] ingest: indexed {len(pairs)} chunks from {CORPUS_DIR.name}/ "
          f"using the {settings.embedder} embedder and the {settings.vector_store} store.")

    # Step 2: ask. The self-healing graph retrieves, grades, generates, and critiques the answer.
    registry = ModelRegistry()
    graph = build_pipeline(
        settings, metered, registry, trace, store=store, embedder=embedder, chunks=pairs
    )
    result = graph.invoke({"question": question, "correction": "", "retries": 0})
    print("\n[2/3] ask: the RAG graph produced an answer.\n")
    print(result["answer"])
    citations = result.get("citations", [])
    if citations:
        print("\nsources:")
        seen: set[str] = set()
        for c in citations:
            if c["chunk_id"] in seen:
                continue
            seen.add(c["chunk_id"])
            print(f"  - {c['title']} ({c['url']})")

    # Step 3: trace. The same trace the obs viewer renders, showing every node and call.
    print("\n[3/3] trace: how the answer was produced.\n")
    print(render_trace(trace.to_dict()))
    return trace


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrated end-to-end RAG walkthrough.")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="the question to ask")
    args = parser.parse_args()
    try:
        run_walkthrough(args.question)
    except Exception as exc:  # noqa: BLE001 - a walkthrough should fail with a readable message
        print(f"\nwalkthrough failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
