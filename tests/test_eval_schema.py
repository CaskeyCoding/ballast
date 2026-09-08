"""EVAL-1/2: the golden loader validates, and the seed set covers every category."""

from __future__ import annotations

from pathlib import Path

import pytest

from ballast.eval.schema import DECLINE_CATEGORIES, load_golden


def test_seed_golden_loads_and_covers_categories() -> None:
    records = load_golden()
    assert len(records) >= 40
    categories = {r.category for r in records}
    assert categories == {"answerable", "multi_hop", "unanswerable", "out_of_corpus", "adversarial"}
    # every decline-category record expects a decline and is not required to cite
    for r in records:
        if r.category in DECLINE_CATEGORIES:
            assert r.expected == "decline" and r.must_cite is False


def test_duplicate_id_fails(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    p.write_text(
        '{"id": "a", "question": "q", "category": "answerable", "expected": "x"}\n'
        '{"id": "a", "question": "q2", "category": "answerable", "expected": "y"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate id"):
        load_golden(p)


def test_decline_category_must_expect_decline(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    p.write_text(
        '{"id": "a", "question": "q", "category": "out_of_corpus", "expected": "paris"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must expect 'decline'"):
        load_golden(p)


def test_malformed_line_fails(tmp_path: Path) -> None:
    p = tmp_path / "g.jsonl"
    p.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        load_golden(p)
