"""DX-1: README quickstart commands match the actual Makefile targets (doc-lint)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _makefile_targets() -> set[str]:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-zA-Z_-]+):", text, re.MULTILINE))


def _readme_make_calls() -> set[str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return set(re.findall(r"\bmake ([a-zA-Z_-]+)", text))


def test_readme_make_commands_exist() -> None:
    referenced = _readme_make_calls()
    targets = _makefile_targets()
    missing = referenced - targets
    assert not missing, f"README references unknown make targets: {sorted(missing)}"
    # sanity: the README must mention the primary entry points
    assert {"ask", "ingest", "eval", "local-ci"} <= referenced


def test_readme_has_diagram_and_three_subsystems() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "```mermaid" in text  # embedded graph diagram
    for subsystem in ("Self-healing RAG", "Guardrails gateway", "Eval CI/CD"):
        assert subsystem in text
