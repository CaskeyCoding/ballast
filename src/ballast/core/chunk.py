"""Heading-aware chunking: split a document into retrievable chunks that keep their provenance.

The body is first split on markdown headings (so a chunk never straddles unrelated sections), then
each section is split into overlapping windows of a target size. Each chunk keeps its source, url,
heading path, and a stable `chunk_id` so retrieval can cite it.

Token budget is approximated by word count to avoid a tokenizer dependency; a real deployment would
swap in the model tokenizer. For the corpus here the approximation is fine.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from ballast.core.corpus import Document

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    url: str
    title: str
    heading_path: str
    chunk_id: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _sections(body: str) -> Iterator[tuple[str, str]]:
    """Yield (heading_path, text) per section; heading_path is the trail of enclosing headings."""
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    path = ""

    def flush() -> Iterator[tuple[str, str]]:
        if buf and any(line.strip() for line in buf):
            yield path, "\n".join(buf).strip()

    for line in body.splitlines():
        m = _HEADING.match(line)
        if m:
            yield from flush()
            buf.clear()
            level, text = len(m.group(1)), m.group(2).strip()
            stack[:] = [(lv, t) for lv, t in stack if lv < level]
            stack.append((level, text))
            path = " > ".join(t for _, t in stack)
        else:
            buf.append(line)
    yield from flush()


def chunk_document(
    doc: Document, *, max_tokens: int = 256, overlap_tokens: int = 40
) -> list[Chunk]:
    """Split `doc` into overlapping, heading-scoped chunks."""
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    step = max_tokens - overlap_tokens
    chunks: list[Chunk] = []
    idx = 0
    for heading_path, text in _sections(doc.body):
        words = text.split()
        if not words:
            continue
        for start in range(0, len(words), step):
            window = words[start : start + max_tokens]
            if not window:
                break
            chunks.append(
                Chunk(
                    text=" ".join(window),
                    source=doc.source,
                    url=doc.url,
                    title=doc.title,
                    heading_path=heading_path or doc.title,
                    chunk_id=f"{doc.path.stem}#{idx}",
                )
            )
            idx += 1
            if start + max_tokens >= len(words):
                break
    return chunks
