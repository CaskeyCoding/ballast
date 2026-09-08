"""DX-5: every ADR follows the template and the index lists them all.

Keeps the decision records honest: a new ADR that skips a section, or one that is not linked from
the index, fails the gate. The required sections come from adr/0000-template.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ADR_DIR = Path(__file__).resolve().parent.parent / "adr"
_INDEX = _ADR_DIR / "index.md"
_REQUIRED_SECTIONS = ["Status", "Context", "Options", "Decision", "Consequences"]

# Numbered records only (0001+), excluding the 0000 template and the index.
_RECORDS = sorted(
    p for p in _ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md") if p.name != "0000-template.md"
)


def test_there_are_records() -> None:
    assert _RECORDS, "no ADR records found in adr/"


@pytest.mark.parametrize("adr", _RECORDS, ids=lambda p: p.name)
def test_record_follows_template(adr: Path) -> None:
    text = adr.read_text(encoding="utf-8")
    headings = set(re.findall(r"^##\s+(.+)$", text, re.M))
    missing = [s for s in _REQUIRED_SECTIONS if s not in headings]
    assert not missing, f"{adr.name} missing sections: {missing}"
    assert re.search(r"^#\s+ADR\s+\d+:", text, re.M), f"{adr.name} missing an `# ADR NNNN:` title"


def test_index_lists_every_record() -> None:
    index = _INDEX.read_text(encoding="utf-8")
    unlisted = [adr.name for adr in _RECORDS if adr.name not in index]
    assert not unlisted, f"adr/index.md does not link: {unlisted}"


def test_template_itself_defines_the_required_sections() -> None:
    template = (_ADR_DIR / "0000-template.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^##\s+(.+)$", template, re.M))
    missing = [s for s in _REQUIRED_SECTIONS if s not in headings]
    assert not missing, f"template is missing sections it requires: {missing}"
