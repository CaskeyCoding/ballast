"""Swap-a-model eval matrix (EVAL-16): run the golden set under each generation model and diff.

The generation model is swapped purely through the LLMClient seam (a ModelRegistry override), so no
code changes between variants. This demonstrates the quality/cost/latency tradeoff concretely.

    python -m ballast.eval.matrix --matrix model=haiku,sonnet [--limit N]
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Callable, Sequence

from ballast.core.config import ModelRegistry, Settings
from ballast.core.cost import CostMeter
from ballast.core.embed import get_embedder
from ballast.core.ingest import CORPUS_DIR, build_index, chunk_corpus
from ballast.core.llm import ClaudeClient
from ballast.core.store import get_store
from ballast.core.trace import MeteredClient, Trace
from ballast.eval.metrics.faithfulness import faithfulness_score
from ballast.eval.runner import ProcessOutput, run_evaluation
from ballast.eval.schema import load_golden
from ballast.gateway.compose import HookContext, compose_post, compose_pre
from ballast.gateway.gateway import Gateway
from ballast.gateway.types import Answer
from ballast.rag.pipeline import build_pipeline

MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
}

_DIFF_KEYS = ("hallucination_rate", "faithfulness_mean", "p95_latency_s", "mean_cost_usd")

# run_one: model_id -> metrics dict
RunOne = Callable[[str], dict[str, float]]


def parse_models(spec: str) -> list[str]:
    """'model=haiku,sonnet' or 'haiku,sonnet' -> ['haiku', 'sonnet']."""
    if "=" in spec:
        spec = spec.split("=", 1)[1]
    return [s.strip() for s in spec.split(",") if s.strip()]


def run_matrix(names: Sequence[str], run_one: RunOne) -> dict[str, dict[str, float]]:
    return {name: run_one(MODEL_ALIASES.get(name, name)) for name in names}


def diff_table(results: dict[str, dict[str, float]], keys: Sequence[str] = _DIFF_KEYS) -> str:
    cols = list(results)
    header = "metric".ljust(22) + "".join(f"{c:>16}" for c in cols)
    lines = [header]
    for key in keys:
        row = "".join(f"{results[c].get(key, 0.0):>16.4f}" for c in cols)
        lines.append(key.ljust(22) + row)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval matrix across generation models.")
    parser.add_argument("--matrix", required=True, help="e.g. model=haiku,sonnet")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N records")
    args = parser.parse_args()

    settings = Settings()
    embedder = get_embedder(settings.embedder, model_name=settings.embed_model)
    store = get_store(settings.vector_store, chroma_dir=settings.chroma_dir)
    build_index(CORPUS_DIR, embedder, store=store)
    pairs = [(c.chunk_id, c.text) for c in chunk_corpus(CORPUS_DIR)]
    base = ClaudeClient(settings.resolve_api_key())
    judge = MeteredClient(base, CostMeter(settings.run_budget_usd * 100), Trace("judge"))
    records = load_golden()
    if args.limit:
        records = records[: args.limit]

    def run_one(model_id: str) -> dict[str, float]:
        registry = ModelRegistry().with_override("generation", model_id)
        ctx = HookContext(base, registry, settings)
        pre, post = compose_pre(settings.pre_hooks, ctx), compose_post(settings.post_hooks, ctx)

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
            return ProcessOutput(
                resp.answer.text, resp.answer.citations, trace.total_latency_s, trace.total_cost_usd
            )

        result = run_evaluation(
            records,
            process=process,
            judge_faithful=lambda q, a, s: faithfulness_score(judge, q, a, s, registry=registry),
            store=store,
        )
        return result.metrics

    print(diff_table(run_matrix(parse_models(args.matrix), run_one)))


if __name__ == "__main__":
    main()
