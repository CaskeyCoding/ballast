"""`make ask` / `python -m ballast.rag.ask "question"`: the full stack, gateway + RAG.

Wires the real runtime: the key from Secrets Manager, a ClaudeClient wrapped in the MeteredClient
(so cost is metered and budget-guarded), an in-process index over the corpus, the self-healing RAG
graph, and the guardrails gateway around it. Prints the guardrail audit, the cited answer, and cost.
`--show-trace` dumps the RAG run trace.
"""

from __future__ import annotations

import argparse
import json
import uuid

from ballast.core.config import ModelRegistry, Settings
from ballast.core.cost import CostMeter
from ballast.core.embed import get_embedder
from ballast.core.ingest import CORPUS_DIR, build_index, chunk_corpus
from ballast.core.llm import ClaudeClient, LLMClient
from ballast.core.store import get_store
from ballast.core.trace import MeteredClient, Trace
from ballast.gateway.compose import HookContext, compose_post, compose_pre
from ballast.gateway.gateway import Gateway
from ballast.gateway.types import Answer
from ballast.obs.store import save_trace
from ballast.rag.pipeline import build_pipeline


def build_gateway(
    trace: Trace,
    *,
    base_client: LLMClient | None = None,
    settings: Settings | None = None,
) -> Gateway:
    settings = settings or Settings()
    base = base_client if base_client is not None else ClaudeClient(settings.resolve_api_key())
    client = MeteredClient(base, CostMeter(settings.run_budget_usd), trace)
    embedder = get_embedder(settings.embedder, model_name=settings.embed_model)
    store = get_store(settings.vector_store, chroma_dir=settings.chroma_dir)
    build_index(CORPUS_DIR, embedder, store=store)
    pairs = [(c.chunk_id, c.text) for c in chunk_corpus(CORPUS_DIR)]
    registry = ModelRegistry()
    graph = build_pipeline(
        settings, client, registry, trace, store=store, embedder=embedder, chunks=pairs
    )

    def handler(question: str, correction: str | None) -> Answer:
        result = graph.invoke({"question": question, "correction": correction or "", "retries": 0})
        return Answer(text=result["answer"], citations=result.get("citations", []))

    ctx = HookContext(client, registry, settings)
    return Gateway(
        handler,
        pre_hooks=compose_pre(settings.pre_hooks, ctx),
        post_hooks=compose_post(settings.post_hooks, ctx),
    )


def run(question: str, *, show_trace: bool = False) -> None:
    trace = Trace(run_id=uuid.uuid4().hex[:8])
    gateway = build_gateway(trace)

    print(f"\nQ: {question}\n")
    response = gateway.process(question)
    save_trace(trace)

    print("Guardrails:")
    for entry in response.audit:
        flag = "BLOCK" if entry.action == "block" else entry.action.upper()
        detail = f" ({entry.rule}: {entry.reason})" if entry.rule else ""
        print(f"  - [{entry.stage}] {entry.hook}: {flag}{detail}")

    print("\nAnswer:\n" + response.answer.text)
    if response.answer.citations:
        print("\nSources:")
        seen = set()
        for c in response.answer.citations:
            if c["chunk_id"] in seen:
                continue
            seen.add(c["chunk_id"])
            print(f"  - {c['title']} ({c['url']})")
    print(
        f"\n[blocked={response.blocked} · cost ${trace.total_cost_usd:.5f} · "
        f"{trace.total_tokens} tokens · {trace.total_latency_s:.2f}s]"
    )
    if show_trace:
        print("\nTrace:\n" + json.dumps(trace.to_dict(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the gateway-wrapped RAG pipeline a question.")
    parser.add_argument("question", help="the question to ask")
    parser.add_argument("--show-trace", action="store_true", help="print the full run trace")
    args = parser.parse_args()
    run(args.question, show_trace=args.show_trace)


if __name__ == "__main__":
    main()
