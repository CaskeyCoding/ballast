"""CORP-1b: ChromaStore round-trips and persists; the store factory selects by config."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("chromadb")  # keep CI lean: skip if chromadb is not installed

from ballast.core.chunk import Chunk  # noqa: E402
from ballast.core.embed import HashingEmbedder  # noqa: E402
from ballast.core.store import (  # noqa: E402
    ChromaStore,
    InMemoryVectorStore,
    get_store,
)


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(text=text, source="s", url="u", title="t", heading_path="t", chunk_id=cid)


def test_factory_selects_backend(tmp_path: Path) -> None:
    assert isinstance(get_store("memory", chroma_dir=tmp_path), InMemoryVectorStore)
    assert isinstance(get_store("chroma", chroma_dir=tmp_path / "c"), ChromaStore)
    with pytest.raises(ValueError, match="unknown vector_store"):
        get_store("nope", chroma_dir=tmp_path)


def test_chroma_round_trip(tmp_path: Path) -> None:
    emb = HashingEmbedder()
    store = ChromaStore(tmp_path / "chroma")
    chunks = {
        "div#0": "diversification spreads risk",
        "comp#0": "compound interest grows over time",
    }
    store.upsert([(_chunk(cid, t), emb.embed(t)) for cid, t in chunks.items()])
    assert store.count() == 2

    got = store.get("div#0")
    assert got is not None and got.text == "diversification spreads risk"

    hits = store.search(emb.embed("compound interest growth"), k=1)
    assert hits[0].chunk.chunk_id == "comp#0"
    assert hits[0].score > 0


def test_chroma_persists_across_instances(tmp_path: Path) -> None:
    emb = HashingEmbedder()
    d = tmp_path / "chroma"
    ChromaStore(d).upsert([(_chunk("a#0", "emergency fund basics"), emb.embed("emergency fund"))])
    reopened = ChromaStore(d)  # fresh instance, same persist dir
    assert reopened.count() == 1
    assert reopened.get("a#0") is not None
