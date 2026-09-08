"""Corpus stats and coverage report (CORP-10).

Eval results are only interpretable against a known corpus shape, so `make corpus-stats` reports the
document count, chunk count, a chunk-size histogram, and per-source coverage.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ballast.core.corpus import load_corpus
from ballast.core.ingest import CORPUS_DIR, chunk_corpus

_BUCKETS = [(0, 50), (50, 100), (100, 200), (200, 10_000)]


def _bucket(n: int) -> str:
    for lo, hi in _BUCKETS:
        if lo <= n < hi:
            return f"{lo}-{hi - 1}" if hi < 10_000 else f"{lo}+"
    return "0-49"


@dataclass
class CorpusStats:
    documents: int
    chunks: int
    histogram: dict[str, int]
    per_source: dict[str, int]


def compute_stats(
    corpus_dir: Path, *, max_tokens: int = 256, overlap_tokens: int = 40
) -> CorpusStats:
    chunks = chunk_corpus(corpus_dir, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    per_source = Counter(c.chunk_id.split("#")[0] for c in chunks)
    histogram = Counter(_bucket(c.word_count) for c in chunks)
    return CorpusStats(
        documents=len(load_corpus(corpus_dir)),
        chunks=len(chunks),
        histogram=dict(histogram),
        per_source=dict(per_source),
    )


def main() -> None:
    stats = compute_stats(CORPUS_DIR)
    print(f"documents: {stats.documents}")
    print(f"chunks: {stats.chunks}")
    print("chunk-size histogram (words):")
    for bucket, count in sorted(stats.histogram.items()):
        print(f"  {bucket}: {count}")
    print("per-source coverage (chunks):")
    for source, count in sorted(stats.per_source.items()):
        print(f"  {source}: {count}")


if __name__ == "__main__":
    main()
