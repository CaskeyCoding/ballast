"""CORP-3: chunks respect the token budget, overlap, and carry the heading path."""

from __future__ import annotations

from pathlib import Path

from ballast.core.chunk import chunk_document
from ballast.core.corpus import Document


def _doc(body: str) -> Document:
    return Document(
        title="T",
        source="S",
        url="http://x",
        published="2026-01-01",
        body=body,
        path=Path("sample.md"),
    )


def test_respects_max_tokens_and_overlaps() -> None:
    words = " ".join(f"w{i}" for i in range(100))
    body = f"# Head\n\n{words}"
    chunks = chunk_document(_doc(body), max_tokens=30, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(c.word_count <= 30 for c in chunks)
    # consecutive chunks overlap: the tail of one reappears at the head of the next
    first_tail = set(chunks[0].text.split()[-10:])
    second_head = set(chunks[1].text.split()[:10])
    assert first_tail & second_head


def test_heading_path_is_captured() -> None:
    body = "# Investing\n\n## Risk\n\nrisk content here\n\n## Return\n\nreturn content here"
    chunks = chunk_document(_doc(body), max_tokens=50, overlap_tokens=10)
    paths = {c.heading_path for c in chunks}
    assert "Investing > Risk" in paths
    assert "Investing > Return" in paths


def test_chunk_ids_are_unique_and_stable() -> None:
    body = "# A\n\n" + " ".join(f"x{i}" for i in range(80))
    ids = [c.chunk_id for c in chunk_document(_doc(body), max_tokens=20, overlap_tokens=5)]
    assert len(ids) == len(set(ids))
    assert ids[0] == "sample#0"
