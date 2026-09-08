"""EVAL-9 runner: run the pipeline over the golden set and compute the aggregate metrics.

The per-question execution is injected (`process`) so the aggregation is unit-testable without the
live model; the CLI wires `process` to the real gateway + RAG. Faithfulness is judged only on
substantive (non-refused) answers, against the text of the chunks the answer cited.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ballast.core.store import VectorStore
from ballast.eval.metrics.hallucination import (
    CaseOutcome,
    hallucination_rate,
    is_hallucination,
)
from ballast.eval.metrics.perf import perf_stats
from ballast.eval.metrics.refusal import is_refusal, refusal_stats
from ballast.eval.metrics.retrieval import (
    ContextScore,
    context_scores,
    mean_context,
    source_of,
)
from ballast.eval.schema import GoldenRecord
from ballast.eval.stats import bootstrap_ci

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "eval" / "results"


@dataclass
class ProcessOutput:
    answer_text: str
    citations: list[dict[str, str]]
    latency_s: float
    cost_usd: float


@dataclass
class CaseResult:
    id: str
    category: str
    should_decline: bool
    refused: bool
    faithfulness: float | None
    latency_s: float
    cost_usd: float


@dataclass
class EvalResult:
    n: int
    metrics: dict[str, float]
    per_category: dict[str, int]
    intervals: dict[str, list[float]] = field(default_factory=dict)
    per_category_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "metrics": self.metrics,
            "intervals": self.intervals,
            "per_category": self.per_category,
            "per_category_metrics": self.per_category_metrics,
            "cases": [asdict(c) for c in self.cases],
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def category_breakdown(cases: Sequence[CaseResult]) -> dict[str, dict[str, float]]:
    """Per-category metrics (EVAL-11), so a regression in one category is not averaged away."""
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for c in cases:
        by_cat[c.category].append(c)
    out: dict[str, dict[str, float]] = {}
    for cat, items in by_cat.items():
        faiths = [c.faithfulness for c in items if c.faithfulness is not None]
        outcomes = [CaseOutcome(c.should_decline, c.refused, c.faithfulness) for c in items]
        out[cat] = {
            "count": float(len(items)),
            "faithfulness_mean": _mean(faiths) if faiths else 1.0,
            "hallucination_rate": hallucination_rate(outcomes),
            "refusal_accuracy": _mean([float(c.should_decline == c.refused) for c in items]),
            "mean_latency_s": _mean([c.latency_s for c in items]),
            "mean_cost_usd": _mean([c.cost_usd for c in items]),
        }
    return out


# process: question -> ProcessOutput. judge_faithful: (question, answer, source_texts) -> 0/1.
Process = Callable[[str], ProcessOutput]
JudgeFaithful = Callable[[str, str, Sequence[str]], float]
JudgeRelevant = Callable[[str, str], float]  # (question, answer) -> 0/1


def run_evaluation(
    records: Sequence[GoldenRecord],
    *,
    process: Process,
    judge_faithful: JudgeFaithful,
    store: VectorStore,
    judge_relevant: JudgeRelevant | None = None,
) -> EvalResult:
    cases: list[CaseResult] = []
    faiths: list[float] = []
    relevancies: list[float] = []
    context: list[ContextScore] = []
    outcomes: list[CaseOutcome] = []
    refusal_items: list[tuple[bool, bool]] = []
    latencies: list[float] = []
    costs: list[float] = []
    per_category: dict[str, int] = {}
    adv_total = 0
    adv_blocked = 0

    for record in records:
        out = process(record.question)
        refused = is_refusal(out.answer_text)
        if record.category == "adversarial":
            adv_total += 1
            adv_blocked += int(refused)  # the gateway/RAG did not comply with the attack
        faithfulness: float | None = None
        if not refused:
            source_texts = [
                chunk.text
                for c in out.citations
                if (chunk := store.get(c.get("chunk_id", ""))) is not None
            ]
            faithfulness = judge_faithful(record.question, out.answer_text, source_texts)
            faiths.append(faithfulness)
            if judge_relevant is not None:
                relevancies.append(judge_relevant(record.question, out.answer_text))
            if record.expected_sources:
                retrieved = {source_of(c.get("chunk_id", "")) for c in out.citations}
                context.append(context_scores(retrieved, set(record.expected_sources)))

        cases.append(
            CaseResult(
                id=record.id,
                category=record.category,
                should_decline=record.should_decline,
                refused=refused,
                faithfulness=faithfulness,
                latency_s=out.latency_s,
                cost_usd=out.cost_usd,
            )
        )
        outcomes.append(CaseOutcome(record.should_decline, refused, faithfulness))
        refusal_items.append((record.should_decline, refused))
        latencies.append(out.latency_s)
        costs.append(out.cost_usd)
        per_category[record.category] = per_category.get(record.category, 0) + 1

    perf = perf_stats(latencies, costs)
    refusal = refusal_stats(refusal_items)
    ctx = mean_context(context)
    metrics = {
        "faithfulness_mean": (sum(faiths) / len(faiths)) if faiths else 1.0,
        "answer_relevancy_mean": (sum(relevancies) / len(relevancies)) if relevancies else 1.0,
        "context_precision_mean": ctx.precision,
        "context_recall_mean": ctx.recall,
        "hallucination_rate": hallucination_rate(outcomes),
        "refusal_accuracy": refusal.accuracy,
        "injection_block_rate": (adv_blocked / adv_total) if adv_total else 1.0,
        "over_refused": float(refusal.over_refused),
        "under_refused": float(refusal.under_refused),
        "p50_latency_s": perf.p50_latency_s,
        "p95_latency_s": perf.p95_latency_s,
        "mean_cost_usd": perf.mean_cost_usd,
        "total_cost_usd": float(sum(costs)),
    }
    halluc_per_case = [float(is_hallucination(o)) for o in outcomes]
    refusal_per_case = [float(sd == dr) for sd, dr in refusal_items]
    intervals = {
        "faithfulness_mean": list(bootstrap_ci(faiths)),
        "answer_relevancy_mean": list(bootstrap_ci(relevancies)),
        "hallucination_rate": list(bootstrap_ci(halluc_per_case)),
        "refusal_accuracy": list(bootstrap_ci(refusal_per_case)),
    }
    return EvalResult(
        n=len(records),
        metrics=metrics,
        per_category=per_category,
        intervals=intervals,
        per_category_metrics=category_breakdown(cases),
        cases=cases,
    )


def write_results(result: EvalResult, sha: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{sha}-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path
