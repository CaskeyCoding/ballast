"""`make eval` / `python -m ballast.eval.run_cli`: the real eval run over the golden set.

Wires the live gateway + RAG as the per-question process, judges faithfulness with a cheap model,
writes a results file, appends the metrics ledger, and prints a summary. `--limit N`, `--only ids`
and `--category cat` run a subset (cheaper and faster for a quick check); subset runs write a
results file but do NOT touch the committed ledger, since their metrics are not comparable to a
full-set baseline. The cache and budget guard keep cost bounded.
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence

from ballast.core.cache import CachingClient, ResponseCache
from ballast.core.config import ModelRegistry, Settings
from ballast.core.cost import CostMeter
from ballast.core.embed import get_embedder
from ballast.core.ingest import CORPUS_DIR, build_index, chunk_corpus
from ballast.core.llm import ClaudeClient, LLMClient
from ballast.core.store import get_store
from ballast.core.trace import MeteredClient, Trace
from ballast.eval.ledger import append_entry, git_sha
from ballast.eval.metrics.faithfulness import faithfulness_score
from ballast.eval.metrics.relevancy import relevancy_score
from ballast.eval.runner import ProcessOutput, run_evaluation, write_results
from ballast.eval.schema import load_golden
from ballast.gateway.compose import HookContext, compose_post, compose_pre
from ballast.gateway.gateway import Gateway
from ballast.gateway.types import Answer
from ballast.obs.store import save_trace
from ballast.rag.pipeline import build_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval suite over the golden set.")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N records")
    parser.add_argument("--only", default=None, help="comma-separated golden ids (subset run)")
    parser.add_argument("--category", default=None, help="run only records in this category")
    args = parser.parse_args()

    settings = Settings()
    registry = ModelRegistry()
    embedder = get_embedder(settings.embedder, model_name=settings.embed_model)
    store = get_store(settings.vector_store, chroma_dir=settings.chroma_dir)
    build_index(CORPUS_DIR, embedder, store=store)
    pairs = [(c.chunk_id, c.text) for c in chunk_corpus(CORPUS_DIR)]
    raw = ClaudeClient(settings.resolve_api_key())
    cache = ResponseCache.load(settings.eval_cache_path) if settings.eval_cache else None
    base: LLMClient = CachingClient(raw, cache) if cache else raw
    judge_client = MeteredClient(base, CostMeter(settings.run_budget_usd * 100), Trace("judge"))

    ctx = HookContext(base, registry, settings)
    pre = compose_pre(settings.pre_hooks, ctx)
    post = compose_post(settings.post_hooks, ctx)

    def process(question: str) -> ProcessOutput:
        trace = Trace(run_id=uuid.uuid4().hex[:8])
        client = MeteredClient(base, CostMeter(settings.run_budget_usd), trace)
        graph = build_pipeline(
            settings, client, registry, trace, store=store, embedder=embedder, chunks=pairs
        )

        def handler(q: str, correction: str | None) -> Answer:
            result = graph.invoke({"question": q, "correction": correction or "", "retries": 0})
            return Answer(text=result["answer"], citations=result.get("citations", []))

        resp = Gateway(handler, pre_hooks=pre, post_hooks=post).process(question)
        save_trace(trace)
        return ProcessOutput(
            resp.answer.text, resp.answer.citations, trace.total_latency_s, trace.total_cost_usd
        )

    def judge_faithful(q: str, a: str, sources: Sequence[str]) -> float:
        return faithfulness_score(judge_client, q, a, sources, registry=registry)

    def judge_relevant(q: str, a: str) -> float:
        return relevancy_score(judge_client, q, a, registry=registry)

    records = load_golden()
    total = len(records)
    if args.category:
        records = [r for r in records if r.category == args.category]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - {r.id for r in records}
        if unknown:
            parser.error(f"unknown golden ids: {sorted(unknown)}")
        records = [r for r in records if r.id in wanted]
    if args.limit:
        records = records[: args.limit]
    if not records:
        parser.error("no golden records selected")
    subset = len(records) < total

    print(f"running eval over {len(records)} records...")
    result = run_evaluation(
        records,
        process=process,
        judge_faithful=judge_faithful,
        store=store,
        judge_relevant=judge_relevant,
    )

    if cache is not None:
        cache.save(settings.eval_cache_path)  # persist for repeatable re-runs

    sha = git_sha()
    path = write_results(result, sha)
    if subset:
        # A partial run's metrics are not comparable to a full-set baseline; keep it out of
        # the committed ledger so the gate never regresses against an apples-to-oranges entry.
        print(f"\nsubset run ({len(records)}/{total} records): ledger NOT updated")
    else:
        append_entry(result.metrics, sha=sha, intervals=result.intervals, n=result.n)

    print(f"\nresults: {path}")
    print(f"per-category: {result.per_category}")
    print("metrics:")
    for k, v in result.metrics.items():
        print(f"  {k}: {v:.4f}")


if __name__ == "__main__":
    main()
