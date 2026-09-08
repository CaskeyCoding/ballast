"""Corpus loader: read markdown documents with provenance frontmatter.

Each corpus file carries `--- source / url / published / title ---` frontmatter so retrieved chunks
can be cited back to where they came from. Loading validates that provenance is present, because an
uncitable chunk defeats the whole grounding story.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("source", "url", "published", "title")


@dataclass(frozen=True)
class Document:
    """One corpus document with its provenance."""

    title: str
    source: str
    url: str
    published: str
    body: str
    path: Path


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.lstrip().startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    return {str(k): str(v) for k, v in meta.items()}, parts[2].strip()


def load_document(path: Path) -> Document:
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
    if missing:
        raise ValueError(f"{path.name} is missing required frontmatter: {', '.join(missing)}")
    return Document(
        title=meta["title"],
        source=meta["source"],
        url=meta["url"],
        published=meta["published"],
        body=body,
        path=path,
    )


def _is_content(path: Path) -> bool:
    # README and underscore-prefixed files are docs about the corpus, not knowledge to ingest.
    return path.name.lower() != "readme.md" and not path.name.startswith("_")


def load_corpus(corpus_dir: Path) -> list[Document]:
    """Load every knowledge `*.md` under `corpus_dir`, validating provenance (sorted)."""
    paths = [p for p in sorted(corpus_dir.glob("*.md")) if _is_content(p)]
    docs = [load_document(p) for p in paths]
    if not docs:
        raise ValueError(f"no corpus documents found under {corpus_dir}")
    return docs
