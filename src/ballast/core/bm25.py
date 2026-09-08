"""A small, dependency-free BM25 keyword index over corpus chunks.

Pure-vector search misses exact-term and rare-entity queries; BM25 covers that lexical axis. Fused
with vector search via RRF (see retrieve.py), it lifts both recall and precision over either alone.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25. `fit` on (chunk_id, text) pairs; `search` returns ranked (chunk_id, score)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._ids: list[str] = []
        self._docs: list[Counter[str]] = []
        self._len: list[int] = []
        self._avgdl: float = 0.0
        self._idf: dict[str, float] = {}

    def fit(self, docs: Sequence[tuple[str, str]]) -> BM25:
        self._ids = [d[0] for d in docs]
        self._docs = [Counter(_tokenize(d[1])) for d in docs]
        self._len = [sum(c.values()) for c in self._docs]
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0
        df: Counter[str] = Counter()
        for doc in self._docs:
            df.update(doc.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        return self

    def search(self, query: str, k: int = 4) -> list[tuple[str, float]]:
        if not self._docs or self._avgdl == 0.0:
            return []
        terms = _tokenize(query)
        scored: list[tuple[str, float]] = []
        for i, doc in enumerate(self._docs):
            dl = self._len[i]
            score = 0.0
            for term in terms:
                f = doc.get(term, 0)
                if not f:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                score += idf * (f * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((self._ids[i], score))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
