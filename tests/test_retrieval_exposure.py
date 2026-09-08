from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest
from scripts.retrieval_exposure import collect_retrieved_sources

from ballast.core.chunk import Chunk
from ballast.core.embed import HashingEmbedder
from ballast.core.retrieve import Retriever
from ballast.core.store import InMemoryVectorStore, Retrieved
from ballast.eval import gate
from ballast.eval.ledger import read_history
from ballast.eval.metrics.exposure import (
    build_exposure_metrics,
    canonical_jsonl_sha256,
    corpus_sha256,
    golden_sha256,
    jensen_shannon_divergence_bits,
)
from ballast.eval.schema import GoldenRecord

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = REPO_ROOT / "scripts" / "retrieval_exposure.py"


class _RecordingRetriever(Retriever):
    def __init__(self, *, store: InMemoryVectorStore, embedder: HashingEmbedder) -> None:
        super().__init__(store=store, embedder=embedder)
        self.calls: list[tuple[str, int]] = []

    def retrieve(
        self, query: str, k: int = 4, *, sources: set[str] | None = None
    ) -> list[Retrieved]:
        self.calls.append((query, k))
        return super().retrieve(query, k=k, sources=sources)


def test_collect_retrieved_sources_calls_direct_retriever_once_per_raw_question() -> None:
    chunks = [
        Chunk("alpha allocation", " alpha ", "u1", "t1", "h1", "a#0"),
        Chunk("beta budgeting", "beta", "u2", "t2", "h2", "b#0"),
        Chunk("gamma growth", "gamma", "u3", "t3", "h3", "c#0"),
        Chunk("delta drawdown", "delta", "u4", "t4", "h4", "d#0"),
    ]
    embedder = HashingEmbedder(dim=4096)
    store = InMemoryVectorStore()
    store.upsert([(chunk, embedder.embed(chunk.text)) for chunk in chunks])
    recording = _RecordingRetriever(store=store, embedder=embedder)
    records = [
        GoldenRecord(
            id="q1", question="  alpha allocation?  ", category="answerable", expected="x"
        ),
        GoldenRecord(id="q2", question="beta budgeting?", category="answerable", expected="y"),
    ]

    retrieved_sources = collect_retrieved_sources(records, recording)

    assert recording.calls == [(records[0].question, 4), (records[1].question, 4)]
    assert len(retrieved_sources) == 8
    assert all(source == source.strip() for source in retrieved_sources)


def test_identical_distributions_have_zero_jsd() -> None:
    assert jensen_shannon_divergence_bits(
        {"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}
    ) == pytest.approx(0.0)


def test_disjoint_singletons_have_one_bit_jsd() -> None:
    assert jensen_shannon_divergence_bits({"a": 1.0}, {"b": 1.0}) == pytest.approx(1.0)


def test_two_equal_sources_have_two_effective_sources() -> None:
    report = build_exposure_metrics(["a", "b"], ["a", "b"])

    assert report["corpus_entropy_bits"] == pytest.approx(1.0)
    assert report["corpus_effective_sources"] == pytest.approx(2.0)


def test_exposure_distributions_sum_to_one() -> None:
    report = build_exposure_metrics(["a", "a", "b"], ["a", "b", "b", "b"])
    sources = report["sources"]
    assert isinstance(sources, list)

    assert sum(row["expected_share"] for row in sources) == pytest.approx(1.0)
    assert sum(row["observed_share"] for row in sources) == pytest.approx(1.0)


def test_effective_sources_stay_within_union_source_count() -> None:
    report = build_exposure_metrics(["a", "a", "b"], ["b", "c", "c"])
    corpus_effective = report["corpus_effective_sources"]
    retrieved_effective = report["retrieved_effective_sources"]

    assert isinstance(corpus_effective, float)
    assert isinstance(retrieved_effective, float)
    assert 1.0 <= corpus_effective <= 3.0
    assert 1.0 <= retrieved_effective <= 3.0


def test_duplicate_retrieved_source_ids_count_as_separate_slots() -> None:
    report = build_exposure_metrics(["a", "b"], ["a", "a", "b"])
    sources = report["sources"]
    assert isinstance(sources, list)

    assert report["retrieved_slot_count"] == 3
    assert sources == [
        {
            "source": "a",
            "expected_share": 0.5,
            "observed_share": pytest.approx(2.0 / 3.0),
            "delta": pytest.approx(1.0 / 6.0),
        },
        {
            "source": "b",
            "expected_share": 0.5,
            "observed_share": pytest.approx(1.0 / 3.0),
            "delta": pytest.approx(-1.0 / 6.0),
        },
    ]


def test_per_source_distribution_rows_are_sorted_over_the_union() -> None:
    report = build_exposure_metrics(["b", "a"], ["c", "b"])

    assert report["sources"] == [
        {"source": "a", "expected_share": 0.5, "observed_share": 0.0, "delta": -0.5},
        {"source": "b", "expected_share": 0.5, "observed_share": 0.5, "delta": 0.0},
        {"source": "c", "expected_share": 0.0, "observed_share": 0.5, "delta": 0.5},
    ]


@pytest.mark.parametrize(
    ("corpus", "retrieved", "reason"),
    [
        ([""], ["a"], "blank_corpus_source"),
        (["a"], [""], "blank_retrieved_source"),
        ([], ["a"], "zero_corpus_chunks"),
        (["a"], [], "zero_retrieved_slots"),
    ],
)
def test_non_estimable_inputs_are_explicit(
    corpus: list[str], retrieved: list[str], reason: str
) -> None:
    report = build_exposure_metrics(corpus, retrieved)

    assert report["status"] == "not_estimable"
    assert report["reason"] == reason
    assert "jensen_shannon_divergence_bits" not in report


def test_canonical_jsonl_hash_uses_compact_sorted_utf8_rows_with_lf_terminators() -> None:
    rows: list[Mapping[str, object]] = [
        {"z": 1, "a": "caf\u00e9"},
        {"b": 1, "a": 2},
    ]

    assert canonical_jsonl_sha256(rows) == (
        "24ec5fa4472a5f1b61c2c933364ab5cb259178ed997c1908570afa621b91f459"
    )


def test_canonical_jsonl_hash_accepts_arbitrary_mapping_rows() -> None:
    rows: list[Mapping[str, object]] = [MappingProxyType({"a": 1})]

    assert canonical_jsonl_sha256(rows) == (
        "e346432021b04179518d9614f3560ccd71354a4ee101ddcb893d6959a9d6301c"
    )


def test_canonical_jsonl_hash_rejects_nonfinite_numbers() -> None:
    with pytest.raises(ValueError, match="JSON compliant"):
        canonical_jsonl_sha256([{"value": float("nan")}])


def test_corpus_hash_uses_exact_six_canonical_chunk_fields() -> None:
    chunks = [
        Chunk(
            text="caf\u00e9",
            source="src",
            url="https://example.test",
            title="Title",
            heading_path="Head",
            chunk_id="doc#0",
        )
    ]

    assert corpus_sha256(chunks) == (
        "5957f7a4f87307d99bf402fcf93159bd8fc7477742c932d172015a2e84252227"
    )


def test_corpus_hash_sorts_chunks_by_chunk_id() -> None:
    first = Chunk("first", "s", "u", "t", "h", "doc#0")
    second = Chunk("second", "s", "u", "t", "h", "doc#1")

    assert corpus_sha256([first, second]) == corpus_sha256([second, first])


def test_corpus_hash_changes_when_chunk_text_changes() -> None:
    chunks_a = [Chunk("before", "s", "u", "t", "h", "doc#0")]
    chunks_with_changed_text = [Chunk("after", "s", "u", "t", "h", "doc#0")]

    assert corpus_sha256(chunks_a) != corpus_sha256(chunks_with_changed_text)


def _golden_records_from_jsonl(source: str) -> list[GoldenRecord]:
    return [GoldenRecord(**json.loads(line)) for line in source.splitlines()]


def test_golden_hash_ignores_json_layout_and_source_line_endings() -> None:
    source_lf = (
        '{"id":"q1","question":"First?","category":"answerable","expected":"One",'
        '"must_cite":true,"expected_sources":["src"],"notes":""}\n'
        '{"id":"q2","question":"Second?","category":"answerable","expected":"Two",'
        '"must_cite":true,"expected_sources":["src"],"notes":""}\n'
    )
    source_crlf = (
        '{ "notes": "", "expected_sources": [ "src" ], "must_cite": true, '
        '"expected": "One", "category": "answerable", "question": "First?", '
        '"id": "q1" }\r\n'
        '{ "question": "Second?", "id": "q2", "expected": "Two", '
        '"category": "answerable", "notes": "", "must_cite": true, '
        '"expected_sources": ["src"] }\r\n'
    )

    assert golden_sha256(_golden_records_from_jsonl(source_lf)) == golden_sha256(
        _golden_records_from_jsonl(source_crlf)
    )


def test_golden_hash_uses_parsed_records_in_file_order() -> None:
    first = GoldenRecord(
        id="q1",
        question="First?",
        category="answerable",
        expected="One",
        expected_sources=["src"],
    )
    second = GoldenRecord(
        id="q2",
        question="Second?",
        category="answerable",
        expected="Two",
        expected_sources=["src"],
    )

    assert golden_sha256([first, second]) == (
        "a57761c16dde409a80c98f02195c242c9d9f099cfc943124e87f20689eaaafbd"
    )
    assert golden_sha256([first, second]) != golden_sha256([second, first])


def test_golden_hash_changes_when_parsed_record_changes() -> None:
    original = GoldenRecord(id="q1", question="Before?", category="answerable", expected="Answer")
    changed = GoldenRecord(id="q1", question="After?", category="answerable", expected="Answer")

    assert golden_sha256([original]) != golden_sha256([changed])


def _write_cli_inputs(tmp_path: Path, *, source: str = "Fixture Source") -> tuple[Path, Path]:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "fixture.md").write_text(
        "---\n"
        f"source: '{source}'\n"
        "url: https://example.test/fixture\n"
        "published: '2026-08-15'\n"
        "title: Fixture\n"
        "---\n"
        "# Allocation\n"
        "alpha allocation balances risk and growth\n",
        encoding="utf-8",
        newline="\n",
    )
    (corpus_dir / "secondary.md").write_text(
        "---\n"
        "source: 'Alpha Source'\n"
        "url: https://example.test/secondary\n"
        "published: '2026-08-15'\n"
        "title: Secondary\n"
        "---\n"
        "# Budgeting\n"
        "beta budgeting preserves liquidity\n",
        encoding="utf-8",
        newline="\n",
    )
    golden_path = tmp_path / "golden.jsonl"
    golden_path.write_text(
        json.dumps(
            {
                "id": "q1",
                "question": "How does alpha allocation balance risk?",
                "category": "answerable",
                "expected": "By balancing risk and growth.",
                "expected_sources": [source],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return corpus_dir, golden_path


def _run_cli(
    corpus_dir: Path, golden_path: Path, output_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--corpus",
        str(corpus_dir),
        "--golden",
        str(golden_path),
    ]
    if output_path is not None:
        command.extend(["--output", str(output_path)])
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def test_cli_requires_output_and_keeps_stdout_empty(tmp_path: Path) -> None:
    corpus_dir, golden_path = _write_cli_inputs(tmp_path)

    completed = _run_cli(corpus_dir, golden_path)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "--output" in completed.stderr
    assert "required" in completed.stderr


def test_cli_writes_one_top_level_strict_json_report(tmp_path: Path) -> None:
    corpus_dir, golden_path = _write_cli_inputs(tmp_path)
    output_path = tmp_path / "retrieval-exposure.json"

    completed = _run_cli(corpus_dir, golden_path, output_path)

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    serialized = output_path.read_text(encoding="utf-8")
    assert "NaN" not in serialized
    assert "Infinity" not in serialized
    assert serialized.endswith("\n")
    payload = json.loads(serialized)
    assert set(payload) == {"retrieval_exposure"}
    report = payload["retrieval_exposure"]
    expected_chunks = [
        Chunk(
            "alpha allocation balances risk and growth",
            "Fixture Source",
            "https://example.test/fixture",
            "Fixture",
            "Allocation",
            "fixture#0",
        ),
        Chunk(
            "beta budgeting preserves liquidity",
            "Alpha Source",
            "https://example.test/secondary",
            "Secondary",
            "Budgeting",
            "secondary#0",
        ),
    ]
    expected_records = [
        GoldenRecord(
            id="q1",
            question="How does alpha allocation balance risk?",
            category="answerable",
            expected="By balancing risk and growth.",
            expected_sources=["Fixture Source"],
        )
    ]
    expected_exposure = build_exposure_metrics(
        ["Fixture Source", "Alpha Source"],
        ["Fixture Source", "Alpha Source"],
    )
    expected_metrics = {
        key: value
        for key, value in expected_exposure.items()
        if key not in {"status", "reason", "retrieved_slot_count", "sources"}
    }

    assert report == {
        "profile": "hashing-baseline-v1",
        "config": {
            "embedder": "HashingEmbedder",
            "embedder_dim": 4096,
            "vector_store": "InMemoryVectorStore",
            "retriever": "Retriever",
            "chunk_size": 256,
            "chunk_overlap": 40,
            "top_k": 4,
            "source_identity": "Retrieved.chunk.source.strip()",
            "corpus_distribution_unit": "chunk",
            "retrieved_distribution_unit": "slot",
        },
        "corpus_sha256": corpus_sha256(expected_chunks),
        "golden_sha256": golden_sha256(expected_records),
        "query_count": len(expected_records),
        "retrieved_slot_count": expected_exposure["retrieved_slot_count"],
        "exclusions": [],
        "status": expected_exposure["status"],
        "reason": None,
        "metrics": expected_metrics,
        "sources": expected_exposure["sources"],
    }
    assert [row["source"] for row in report["sources"]] == [
        "Alpha Source",
        "Fixture Source",
    ]


def test_cli_not_estimable_is_a_successful_diagnostic_state(tmp_path: Path) -> None:
    corpus_dir, golden_path = _write_cli_inputs(tmp_path, source="   ")
    output_path = tmp_path / "not-estimable.json"

    completed = _run_cli(corpus_dir, golden_path, output_path)

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    serialized = output_path.read_text(encoding="utf-8")
    assert "NaN" not in serialized
    assert "Infinity" not in serialized
    report = json.loads(serialized)["retrieval_exposure"]
    assert report["status"] == "not_estimable"
    assert report["reason"] == "blank_corpus_source"


def test_cli_failure_writes_strict_artifact_and_exits_one(tmp_path: Path) -> None:
    _, golden_path = _write_cli_inputs(tmp_path)
    output_path = tmp_path / "failed.json"

    completed = _run_cli(tmp_path / "missing-corpus", golden_path, output_path)

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "ValueError" in completed.stderr
    assert str(tmp_path) not in completed.stderr
    serialized = output_path.read_text(encoding="utf-8")
    assert "NaN" not in serialized
    assert "Infinity" not in serialized
    payload = json.loads(serialized)
    assert set(payload) == {"retrieval_exposure"}
    assert payload["retrieval_exposure"] == {
        "error_class": "ValueError",
        "profile": "hashing-baseline-v1",
        "reason": "execution_error",
        "status": "failed",
    }


def test_cli_artifact_leaves_history_and_gate_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus_dir, golden_path = _write_cli_inputs(tmp_path)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    history_path = eval_dir / "history.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "sha": "fixture",
                "timestamp": "2026-08-15T00:00:00+00:00",
                "metrics": {
                    "hallucination_rate": 0.0,
                    "refusal_accuracy": 1.0,
                    "injection_block_rate": 1.0,
                    "p95_latency_s": 1.0,
                },
                "intervals": {},
                "n": 1,
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setattr(gate, "read_history", lambda: read_history(history_path))
    monkeypatch.setattr(gate, "commits_behind", lambda _sha: 0)
    before_bytes = history_path.read_bytes()
    before_entries = read_history(history_path)
    before_gate_exit = gate.main()
    capsys.readouterr()

    output_path = eval_dir / "retrieval-exposure.json"
    completed = _run_cli(corpus_dir, golden_path, output_path)

    after_gate_exit = gate.main()
    capsys.readouterr()
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert history_path.read_bytes() == before_bytes
    assert read_history(history_path) == before_entries
    assert after_gate_exit == before_gate_exit == 0
    assert set(json.loads(output_path.read_text(encoding="utf-8"))) == {"retrieval_exposure"}
