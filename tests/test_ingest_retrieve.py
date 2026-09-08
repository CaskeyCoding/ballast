"""CORP-5 + CORP-6: ingest is idempotent and retrieval finds the right corpus doc."""

from __future__ import annotations

from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever


def test_ingest_seed_corpus_and_idempotent() -> None:
    emb = HashingEmbedder()
    store = build_index(CORPUS_DIR, emb)
    count = store.count()
    assert count >= 8  # at least one chunk per seed doc
    build_index(CORPUS_DIR, emb, store=store)  # re-ingest into same store
    assert store.count() == count  # idempotent: keyed by chunk_id


def test_retriever_finds_relevant_doc() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    hits = retriever.retrieve("what is dollar cost averaging", k=3)
    assert hits
    top_sources = {h.chunk.chunk_id.split("#")[0] for h in hits}
    assert "dollar-cost-averaging" in top_sources


def test_retriever_unrelated_query_lower_score() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    on_topic = retriever.retrieve("how do index funds work", k=1)[0].score
    off_topic = retriever.retrieve("xyzzy quux frobnicate", k=1)[0].score
    assert on_topic > off_topic
