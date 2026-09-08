"""Pure information-theory metrics for retrieval source exposure."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence

from ballast.core.chunk import Chunk
from ballast.eval.schema import GoldenRecord


def canonical_jsonl_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    """Hash compact, sorted-key UTF-8 JSONL with one LF per parsed row."""
    encoded = "".join(
        json.dumps(
            dict(row),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
        for row in rows
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def corpus_sha256(chunks: Sequence[Chunk]) -> str:
    """Hash the canonical six-field representation of chunks by chunk ID."""
    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "url": chunk.url,
            "title": chunk.title,
            "heading_path": chunk.heading_path,
            "text": chunk.text,
        }
        for chunk in sorted(chunks, key=lambda chunk: chunk.chunk_id)
    ]
    return canonical_jsonl_sha256(rows)


def golden_sha256(records: Sequence[GoldenRecord]) -> str:
    """Hash parsed golden records in their supplied file order."""
    return canonical_jsonl_sha256([record.model_dump() for record in records])


def shannon_entropy_bits(shares: Mapping[str, float]) -> float:
    """Return Shannon entropy in bits for a source-share distribution."""
    return -sum(share * math.log2(share) for share in shares.values() if share > 0.0)


def _kl_bits(distribution: Mapping[str, float], reference: Mapping[str, float]) -> float:
    return sum(
        share * math.log2(share / reference[source])
        for source, share in distribution.items()
        if share > 0.0
    )


def jensen_shannon_divergence_bits(
    expected: Mapping[str, float], observed: Mapping[str, float]
) -> float:
    """Return the base-2 Jensen-Shannon divergence of two distributions."""
    keys = sorted(set(expected) | set(observed))
    midpoint = {key: (expected.get(key, 0.0) + observed.get(key, 0.0)) / 2.0 for key in keys}
    return 0.5 * _kl_bits(expected, midpoint) + 0.5 * _kl_bits(observed, midpoint)


def _shares(sources: Sequence[str]) -> dict[str, float]:
    counts = Counter(sources)
    total = len(sources)
    return {source: count / total for source, count in counts.items()}


def build_exposure_metrics(
    corpus_sources: Sequence[str], retrieved_sources: Sequence[str]
) -> dict[str, object]:
    """Compare corpus chunk share with retrieved slot share by source."""
    reason: str | None = None
    if "" in corpus_sources:
        reason = "blank_corpus_source"
    elif "" in retrieved_sources:
        reason = "blank_retrieved_source"
    elif not retrieved_sources:
        reason = "zero_retrieved_slots"
    elif not corpus_sources:
        reason = "zero_corpus_chunks"
    if reason is not None:
        return {
            "status": "not_estimable",
            "reason": reason,
            "corpus_chunk_count": len(corpus_sources),
            "retrieved_slot_count": len(retrieved_sources),
        }

    expected = _shares(corpus_sources)
    observed = _shares(retrieved_sources)
    corpus_entropy = shannon_entropy_bits(expected)
    retrieved_entropy = shannon_entropy_bits(observed)
    source_rows = [
        {
            "source": source,
            "expected_share": expected.get(source, 0.0),
            "observed_share": observed.get(source, 0.0),
            "delta": observed.get(source, 0.0) - expected.get(source, 0.0),
        }
        for source in sorted(set(expected) | set(observed))
    ]
    return {
        "status": "ok",
        "corpus_chunk_count": len(corpus_sources),
        "retrieved_slot_count": len(retrieved_sources),
        "jensen_shannon_divergence_bits": jensen_shannon_divergence_bits(expected, observed),
        "corpus_entropy_bits": corpus_entropy,
        "retrieved_entropy_bits": retrieved_entropy,
        "corpus_effective_sources": 2.0**corpus_entropy,
        "retrieved_effective_sources": 2.0**retrieved_entropy,
        "sources": source_rows,
    }
