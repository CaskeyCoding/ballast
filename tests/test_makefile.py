"""DX-4: the Makefile is a complete, self-describing command surface.

There is no `make` binary in CI here, so these tests parse the Makefile the same way the `help`
target's grep does: a target is `name: ... ## description`. They assert every target carries a
description, every target is declared `.PHONY`, and every `make <target>` the README mentions is a
real target. A missing description or an undocumented README target fails the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MAKEFILE = _ROOT / "Makefile"
_README = _ROOT / "README.md"

# Matches the help target's own pattern: `^[a-zA-Z_-]+:.*?## .*$`
_TARGET_RE = re.compile(r"^([a-zA-Z_-]+):.*?## (.+)$", re.M)
_ANY_RULE_RE = re.compile(r"^([a-zA-Z_-]+):", re.M)


def _described_targets() -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _TARGET_RE.finditer(_MAKEFILE.read_text())}


def _phony_targets() -> set[str]:
    text = _MAKEFILE.read_text()
    # `.PHONY:` may span lines via trailing backslash continuations.
    block = re.search(r"\.PHONY:((?:[^\n\\]|\\\n)*)", text)
    assert block, ".PHONY declaration not found"
    return set(block.group(1).replace("\\\n", " ").split())


def test_every_target_has_a_description() -> None:
    described = _described_targets()
    all_rules = set(_ANY_RULE_RE.findall(_MAKEFILE.read_text()))
    undescribed = all_rules - set(described)
    assert not undescribed, f"Makefile targets missing a ## description: {sorted(undescribed)}"
    assert all(desc for desc in described.values())


def test_every_target_is_declared_phony() -> None:
    described = _described_targets()
    phony = _phony_targets()
    missing = set(described) - phony
    assert not missing, f"targets not listed in .PHONY: {sorted(missing)}"


def test_readme_make_targets_all_exist() -> None:
    described = _described_targets()
    referenced = set(re.findall(r"\bmake ([a-zA-Z_-]+)", _README.read_text()))
    unknown = referenced - set(described)
    assert not unknown, f"README references make targets that do not exist: {sorted(unknown)}"
