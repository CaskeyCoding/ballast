"""CORP-10: corpus stats over the seed corpus."""

from __future__ import annotations

from ballast.core.corpus_stats import compute_stats
from ballast.core.ingest import CORPUS_DIR


def test_stats_over_seed_corpus() -> None:
    stats = compute_stats(CORPUS_DIR)
    assert stats.documents >= 8
    assert stats.chunks >= 8
    # per-source coverage sums to the chunk count and names real docs
    assert sum(stats.per_source.values()) == stats.chunks
    assert "diversification" in stats.per_source
    # histogram counts sum to the chunk count
    assert sum(stats.histogram.values()) == stats.chunks
