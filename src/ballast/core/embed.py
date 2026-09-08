"""Embeddings behind a small protocol so the backend is swappable.

The default `HashingEmbedder` is a dependency-light term-frequency hashing vectorizer: deterministic
(hashlib, not the salted builtin hash), no model download, and strong enough for retrieval over a
small focused corpus. `SentenceTransformerEmbedder` is the quality upgrade (CORP-4b) and is imported
lazily so torch is only needed if you actually opt in.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "the a an of to and or in is are be as at by for it its on that this with you your from "
    "can will not but if then than into over more most can may which who whom whose".split()
)


@runtime_checkable
class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> Vector: ...


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


class HashingEmbedder:
    """Deterministic term-frequency hashing embedder with L2-normalized vectors."""

    def __init__(self, dim: int = 4096) -> None:
        self.dim = dim

    def _bucket(self, token: str) -> int:
        return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim

    def embed(self, text: str) -> Vector:
        vec: Vector = np.zeros(self.dim, dtype=np.float64)
        for token in _tokens(text):
            vec[self._bucket(token)] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def embed_batch(self, texts: Sequence[str]) -> Vector:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float64)
        return np.vstack([self.embed(t) for t in texts])


class SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers. torch is imported lazily on first use."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self) -> int:
        return int(self._ensure_model().get_sentence_embedding_dimension())

    def embed(self, text: str) -> Vector:
        vec = self._ensure_model().encode([text], normalize_embeddings=True)[0]
        return np.asarray(vec, dtype=np.float64)

    def embed_batch(self, texts: Sequence[str]) -> Vector:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float64)
        mat = self._ensure_model().encode(list(texts), normalize_embeddings=True)
        return np.asarray(mat, dtype=np.float64)


def get_embedder(
    name: str = "sentence-transformers", *, model_name: str = "all-MiniLM-L6-v2"
) -> Embedder:
    """Factory: pick the embedder backend by name. `hashing` needs no torch."""
    if name == "hashing":
        return HashingEmbedder()
    if name in ("sentence-transformers", "st"):
        return SentenceTransformerEmbedder(model_name=model_name)
    raise ValueError(f"unknown embedder {name!r}; use 'sentence-transformers' or 'hashing'")
