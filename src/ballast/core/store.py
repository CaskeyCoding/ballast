"""Vector store behind a protocol; an in-memory cosine store as the default backend.

`InMemoryVectorStore` keeps (chunk, vector) pairs keyed by chunk_id (so upsert is idempotent) and
ranks by cosine similarity. Vectors are stored normalized, so a dot product is the cosine. A
persistent `ChromaStore` behind the same protocol is queued as CORP-1b; nothing above the protocol
needs to change to swap it in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np

from ballast.core.chunk import Chunk
from ballast.core.embed import Vector


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, records: Sequence[tuple[Chunk, Vector]]) -> None: ...

    def search(self, query_vector: Vector, k: int = 4) -> list[Retrieved]: ...

    def count(self) -> int: ...

    def get(self, chunk_id: str) -> Chunk | None: ...


@dataclass
class InMemoryVectorStore:
    _items: dict[str, tuple[Chunk, Vector]] = field(default_factory=dict)

    def upsert(self, records: Sequence[tuple[Chunk, Vector]]) -> None:
        for chunk, vector in records:
            self._items[chunk.chunk_id] = (chunk, vector)

    def count(self) -> int:
        return len(self._items)

    def get(self, chunk_id: str) -> Chunk | None:
        item = self._items.get(chunk_id)
        return item[0] if item else None

    def search(self, query_vector: Vector, k: int = 4) -> list[Retrieved]:
        if not self._items:
            return []
        ids = list(self._items)
        matrix = np.vstack([self._items[i][1] for i in ids])
        scores = matrix @ query_vector
        order = np.argsort(scores)[::-1][:k]
        return [Retrieved(chunk=self._items[ids[i]][0], score=float(scores[i])) for i in order]


class ChromaStore:
    """Persistent `VectorStore` backed by Chroma. We pass our own embeddings; Chroma stores them.

    Chunk fields ride along as Chroma metadata + the document text, so search and get reconstruct a
    full Chunk for citation. Cosine space, so similarity is 1 - distance.
    """

    def __init__(self, persist_dir: Path, collection: str = "corpus") -> None:
        import chromadb

        client = chromadb.PersistentClient(path=str(persist_dir))
        # Chroma's typed return shapes (Optional, broad Mapping) fight static indexing; the
        # collection is a thin data conduit, so treat it as Any and rely on the round-trip test.
        self._col: Any = client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    @staticmethod
    def _to_chunk(chunk_id: str, text: str, meta: dict[str, Any]) -> Chunk:
        return Chunk(
            text=text,
            source=str(meta.get("source", "")),
            url=str(meta.get("url", "")),
            title=str(meta.get("title", "")),
            heading_path=str(meta.get("heading_path", "")),
            chunk_id=chunk_id,
        )

    def upsert(self, records: Sequence[tuple[Chunk, Vector]]) -> None:
        if not records:
            return
        self._col.upsert(
            ids=[c.chunk_id for c, _ in records],
            embeddings=[[float(x) for x in v] for _, v in records],
            metadatas=[
                {"source": c.source, "url": c.url, "title": c.title, "heading_path": c.heading_path}
                for c, _ in records
            ],
            documents=[c.text for c, _ in records],
        )

    def count(self) -> int:
        return int(self._col.count())

    def get(self, chunk_id: str) -> Chunk | None:
        res = self._col.get(ids=[chunk_id])
        if not res["ids"]:
            return None
        return self._to_chunk(chunk_id, res["documents"][0], res["metadatas"][0])

    def search(self, query_vector: Vector, k: int = 4) -> list[Retrieved]:
        res = self._col.query(query_embeddings=[[float(x) for x in query_vector]], n_results=k)
        out: list[Retrieved] = []
        for i, cid in enumerate(res["ids"][0]):
            chunk = self._to_chunk(cid, res["documents"][0][i], res["metadatas"][0][i])
            out.append(Retrieved(chunk=chunk, score=1.0 - float(res["distances"][0][i])))
        return out


def get_store(name: str, *, chroma_dir: Path) -> VectorStore:
    """Factory: pick the vector-store backend by config name. `memory` is the default."""
    if name == "memory":
        return InMemoryVectorStore()
    if name == "chroma":
        return ChromaStore(chroma_dir)
    raise ValueError(f"unknown vector_store {name!r}; use 'memory' or 'chroma'")
