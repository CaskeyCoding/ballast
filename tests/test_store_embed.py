"""CORP-1 + CORP-4: hashing embedder determinism and in-memory cosine retrieval."""

from __future__ import annotations

import numpy as np
import pytest

from ballast.core.chunk import Chunk
from ballast.core.embed import (
    Embedder,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)
from ballast.core.store import InMemoryVectorStore, VectorStore


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(text=text, source="s", url="u", title="t", heading_path="t", chunk_id=cid)


def test_embedder_satisfies_protocol_and_is_deterministic() -> None:
    emb = HashingEmbedder(dim=512)
    assert isinstance(emb, Embedder)
    v1 = emb.embed("compound interest grows over time")
    v2 = emb.embed("compound interest grows over time")
    assert np.allclose(v1, v2)  # deterministic across calls (hashlib, not salted hash)
    assert abs(float(np.linalg.norm(v1)) - 1.0) < 1e-9  # L2 normalized


def test_factory_selects_backend_by_name() -> None:
    # The ST branch must not load the model (no torch needed) just to be constructed.
    assert isinstance(get_embedder("hashing"), HashingEmbedder)
    assert isinstance(get_embedder("sentence-transformers"), SentenceTransformerEmbedder)
    with pytest.raises(ValueError, match="unknown embedder"):
        get_embedder("nope")


def test_store_is_protocol_and_upsert_idempotent() -> None:
    store = InMemoryVectorStore()
    assert isinstance(store, VectorStore)
    emb = HashingEmbedder(dim=512)
    rec = [
        (_chunk("c#0", "diversification spreads risk"), emb.embed("diversification spreads risk"))
    ]
    store.upsert(rec)
    store.upsert(rec)  # same chunk_id, must not duplicate
    assert store.count() == 1


def test_search_ranks_relevant_chunk_first() -> None:
    emb = HashingEmbedder(dim=1024)
    chunks = {
        "div": "diversification means spreading money across many investments",
        "fee": "an expense ratio is the annual cost of a fund",
        "comp": "compound interest is interest earned on interest over time",
    }
    store = InMemoryVectorStore()
    store.upsert([(_chunk(cid, txt), emb.embed(txt)) for cid, txt in chunks.items()])
    top = store.search(emb.embed("how does compounding interest work"), k=1)
    assert top[0].chunk.chunk_id == "comp"
    assert top[0].score > 0
