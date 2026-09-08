"""EVAL-6/9/13/14: runner aggregation, the gate logic, and the ledger."""

from __future__ import annotations

from pathlib import Path

from ballast.core.chunk import Chunk
from ballast.core.embed import HashingEmbedder
from ballast.core.store import InMemoryVectorStore
from ballast.eval.gate import check_gate
from ballast.eval.ledger import append_entry, read_history
from ballast.eval.runner import ProcessOutput, run_evaluation
from ballast.eval.schema import GoldenRecord
from ballast.gateway.fallback import INSUFFICIENT

_TH = {
    "hallucination_rate_max": 0.05,
    "refusal_correctness_min": 0.90,
    "latency_p95_regress_frac": 0.20,
}
_CIT = [{"title": "t", "source": "s", "url": "u", "chunk_id": "div#0"}]


def _store() -> InMemoryVectorStore:
    emb = HashingEmbedder()
    chunk = Chunk("diversification spreads risk", "s", "u", "t", "t", "div#0")
    store = InMemoryVectorStore()
    store.upsert([(chunk, emb.embed(chunk.text))])
    return store


def test_run_evaluation_aggregates_metrics() -> None:
    records = [
        GoldenRecord(id="a1", question="qa", category="answerable", expected="x"),
        GoldenRecord(id="a2", question="qb", category="answerable", expected="y"),
        GoldenRecord(id="u1", question="qc", category="unanswerable", expected="decline"),
        GoldenRecord(id="u2", question="qd", category="out_of_corpus", expected="decline"),
    ]
    outputs = {
        "qa": ProcessOutput("grounded answer [1]", _CIT, 1.0, 0.01),  # faithful answer
        "qb": ProcessOutput("hallucinated answer [1]", _CIT, 2.0, 0.02),  # unfaithful answer
        "qc": ProcessOutput(INSUFFICIENT, [], 0.5, 0.0),  # correctly declines
        "qd": ProcessOutput(
            "Paris is the capital [1]", _CIT, 3.0, 0.03
        ),  # answered, should decline
    }

    def process(q: str) -> ProcessOutput:
        return outputs[q]

    def judge(q: str, a: str, s: list[str]) -> float:
        return 0.0 if "hallucinated" in a else 1.0

    result = run_evaluation(records, process=process, judge_faithful=judge, store=_store())

    # hallucinations: a2 (unfaithful) + u2 (answered when should decline) = 2/4
    assert result.metrics["hallucination_rate"] == 0.5
    # refusal correct: a1, a2 (answered, ok), u1 (declined, ok); u2 under-refused -> 3/4
    assert result.metrics["refusal_accuracy"] == 0.75
    assert result.metrics["under_refused"] == 1.0
    assert result.metrics["p50_latency_s"] == 1.5  # median of [1,2,0.5,3]
    assert result.per_category["answerable"] == 2
    assert result.n == 4


def test_gate_flags_hallucination_and_passes_clean() -> None:
    fail = check_gate(
        {"hallucination_rate": 0.10, "refusal_accuracy": 1.0, "p95_latency_s": 5.0}, _TH
    )
    assert any("hallucination" in f for f in fail)
    ok = check_gate(
        {"hallucination_rate": 0.02, "refusal_accuracy": 0.95, "p95_latency_s": 5.0}, _TH
    )
    assert ok == []


def test_gate_flags_latency_regression() -> None:
    fail = check_gate(
        {"hallucination_rate": 0.0, "refusal_accuracy": 1.0, "p95_latency_s": 10.0},
        _TH,
        previous={"p95_latency_s": 5.0},
    )
    assert any("latency" in f for f in fail)


def test_ledger_append_and_read(tmp_path: Path) -> None:
    p = tmp_path / "history.jsonl"
    append_entry({"hallucination_rate": 0.0}, path=p, sha="abc123", timestamp="2026-06-26T00:00:00")
    append_entry({"hallucination_rate": 0.1}, path=p, sha="def456", timestamp="2026-06-26T01:00:00")
    history = read_history(p)
    assert len(history) == 2
    assert history[-1]["sha"] == "def456"


def test_ledger_records_workload_size_when_given(tmp_path: Path) -> None:
    # EVAL-23: n lets the gate compare latency/cost like-for-like across runs
    p = tmp_path / "history.jsonl"
    append_entry({"hallucination_rate": 0.0}, path=p, sha="abc123", n=89)
    append_entry({"hallucination_rate": 0.0}, path=p, sha="def456")
    history = read_history(p)
    assert history[0]["n"] == 89
    assert "n" not in history[1]  # older-style entries simply omit it
