"""Golden dataset schema + a strict loader.

Every record is validated; a malformed line, a duplicate id, or a decline-category record not marked
as a decline fails loudly. The harness reads exactly this shape, so it must be trustworthy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = REPO_ROOT / "eval" / "golden.jsonl"

# Categories. The decline categories expect the pipeline to refuse rather than answer.
Category = Literal["answerable", "multi_hop", "unanswerable", "out_of_corpus", "adversarial"]
DECLINE_CATEGORIES = {"unanswerable", "out_of_corpus", "adversarial"}
DECLINE = "decline"


class GoldenRecord(BaseModel):
    id: str
    question: str
    category: Category
    expected: str  # a reference answer, or "decline" for the decline categories
    must_cite: bool = True
    expected_sources: list[str] = []  # corpus doc stems a good retrieval should surface
    notes: str = ""

    @property
    def should_decline(self) -> bool:
        return self.category in DECLINE_CATEGORIES


def load_golden(path: Path | None = None) -> list[GoldenRecord]:
    path = path or GOLDEN_PATH
    records: list[GoldenRecord] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = GoldenRecord(**json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"golden line {lineno} invalid: {exc}") from exc
        if record.id in seen:
            raise ValueError(f"golden line {lineno}: duplicate id {record.id!r}")
        if record.should_decline and record.expected != DECLINE:
            raise ValueError(
                f"golden line {lineno}: {record.category} record must expect 'decline'"
            )
        seen.add(record.id)
        records.append(record)
    if not records:
        raise ValueError(f"no golden records found in {path}")
    return records
