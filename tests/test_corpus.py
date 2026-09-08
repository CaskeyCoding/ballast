"""CORP-2: corpus loads with valid provenance; missing frontmatter fails; README excluded."""

from __future__ import annotations

from pathlib import Path

import pytest

from ballast.core.corpus import REQUIRED_FIELDS, load_corpus, load_document

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"


def test_seed_corpus_loads_at_least_eight_docs() -> None:
    docs = load_corpus(CORPUS_DIR)
    assert len(docs) >= 8
    for doc in docs:
        for field in REQUIRED_FIELDS:
            assert getattr(doc, field), f"{doc.path.name} missing {field}"
        assert doc.body.strip()


def test_readme_is_excluded_from_knowledge() -> None:
    names = {d.path.name for d in load_corpus(CORPUS_DIR)}
    assert "README.md" not in names


def test_missing_frontmatter_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("---\ntitle: No Source\n---\nbody", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required frontmatter"):
        load_document(bad)
