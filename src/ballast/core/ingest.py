"""Ingestion: load the corpus, chunk it, embed each chunk, and upsert into a vector store.

`build_index` is the reusable core (used by `make ask` to build an index in-process, which is fast
for this corpus) and by the `make ingest` CLI, which reports a chunk count. Upsert is keyed by
chunk_id, so re-running is idempotent.
"""

from __future__ import annotations

from pathlib import Path

from ballast.core.chunk import Chunk, chunk_document
from ballast.core.config import Settings
from ballast.core.corpus import load_corpus
from ballast.core.embed import Embedder, get_embedder
from ballast.core.store import InMemoryVectorStore, VectorStore, get_store

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = REPO_ROOT / "corpus"


def chunk_corpus(
    corpus_dir: Path, *, max_tokens: int = 256, overlap_tokens: int = 40
) -> list[Chunk]:
    """Load and chunk the corpus once. Shared by the vector index and the BM25 keyword index."""
    chunks: list[Chunk] = []
    for doc in load_corpus(corpus_dir):
        chunks.extend(chunk_document(doc, max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return chunks


def build_index(
    corpus_dir: Path,
    embedder: Embedder,
    *,
    max_tokens: int = 256,
    overlap_tokens: int = 40,
    store: VectorStore | None = None,
) -> VectorStore:
    store = store if store is not None else InMemoryVectorStore()
    chunks = chunk_corpus(corpus_dir, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    store.upsert([(c, embedder.embed(c.text)) for c in chunks])
    return store


def main() -> None:
    settings = Settings()
    embedder = get_embedder(settings.embedder, model_name=settings.embed_model)
    store = get_store(settings.vector_store, chroma_dir=settings.chroma_dir)
    build_index(CORPUS_DIR, embedder, store=store)
    print(
        f"ingested {store.count()} chunks from {CORPUS_DIR} "
        f"using {settings.embedder} + {settings.vector_store}"
    )


if __name__ == "__main__":
    main()
