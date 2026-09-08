#!/usr/bin/env python3
"""Deterministic, report-only retrieval source exposure diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, chunk_corpus
from ballast.core.retrieve import Retriever
from ballast.core.store import InMemoryVectorStore
from ballast.eval.metrics.exposure import (
    build_exposure_metrics,
    corpus_sha256,
    golden_sha256,
)
from ballast.eval.schema import GOLDEN_PATH, GoldenRecord, load_golden

PROFILE = "hashing-baseline-v1"


def collect_retrieved_sources(records: Sequence[GoldenRecord], retriever: Retriever) -> list[str]:
    """Collect one stripped source ID per returned direct-retrieval slot."""
    retrieved_sources: list[str] = []
    for record in records:
        hits = retriever.retrieve(record.question, k=4)
        retrieved_sources.extend(hit.chunk.source.strip() for hit in hits)
    return retrieved_sources


def run_exposure(corpus_dir: Path, golden_path: Path) -> dict[str, object]:
    """Run the frozen hashing baseline and return its isolated report payload."""
    chunks = chunk_corpus(corpus_dir, max_tokens=256, overlap_tokens=40)
    records = load_golden(golden_path)
    embedder = HashingEmbedder(dim=4096)
    store = InMemoryVectorStore()
    store.upsert(  # type: ignore[arg-type]
        (chunk, embedder.embed(chunk.text)) for chunk in chunks
    )
    retriever = Retriever(store=store, embedder=embedder)
    retrieved_sources = collect_retrieved_sources(records, retriever)
    exposure = build_exposure_metrics([chunk.source.strip() for chunk in chunks], retrieved_sources)
    status = exposure.pop("status")
    reason = exposure.pop("reason", None)
    sources = exposure.pop("sources", [])
    retrieved_slot_count = exposure.pop("retrieved_slot_count")

    return {
        "retrieval_exposure": {
            "profile": PROFILE,
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
            "corpus_sha256": corpus_sha256(chunks),
            "golden_sha256": golden_sha256(records),
            "query_count": len(records),
            "retrieved_slot_count": retrieved_slot_count,
            "exclusions": [],
            "status": status,
            "reason": reason,
            "metrics": exposure,
            "sources": sources,
        }
    }


def _strict_json(payload: dict[str, object]) -> str:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _failed_payload(exc: Exception) -> dict[str, object]:
    return {
        "retrieval_exposure": {
            "profile": PROFILE,
            "status": "failed",
            "reason": "execution_error",
            "error_class": type(exc).__name__,
        }
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        payload = run_exposure(args.corpus, args.golden)
        serialized = _strict_json(payload)
        exit_code = 0
    except Exception as exc:
        payload = _failed_payload(exc)
        serialized = _strict_json(payload)
        exit_code = 1
        sys.stderr.write(f"retrieval exposure failed: {type(exc).__name__}: execution_error\n")
    args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
