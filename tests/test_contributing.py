"""DX-6: doc-lint for CONTRIBUTING.md.

The contributing guide is only useful if its commands and paths are real. These tests extract every
repo-relative path it names (anchored on the known top-level directories) and every `make <target>`
it mentions, and assert each one exists. A renamed script or a stale path fails the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "CONTRIBUTING.md"
_MAKEFILE = _ROOT / "Makefile"

# Repo paths are anchored on a known top-level dir so every match is a real reference, not prose.
_TOP = "src|tests|scripts|specs|adr|corpus|examples"
_PATH_RE = re.compile(rf"\b((?:{_TOP})/[\w./-]*)")
_MAKE_RE = re.compile(r"\bmake ([a-z][a-z-]*)")


def _doc() -> str:
    return _DOC.read_text(encoding="utf-8")


def test_contributing_exists() -> None:
    assert _DOC.is_file(), "CONTRIBUTING.md is missing"


def test_referenced_paths_exist() -> None:
    missing = []
    for raw in set(_PATH_RE.findall(_doc())):
        token = raw.rstrip("/.,)")  # strip trailing punctuation from prose
        if not token:
            continue
        if not (_ROOT / token).exists():
            missing.append(token)
    assert not missing, f"CONTRIBUTING.md references paths that do not exist: {sorted(missing)}"


def test_referenced_make_targets_exist() -> None:
    described = set(re.findall(r"^([a-zA-Z_-]+):.*?## ", _MAKEFILE.read_text(), re.M))
    referenced = set(_MAKE_RE.findall(_doc()))
    unknown = referenced - described
    assert (
        not unknown
    ), f"CONTRIBUTING.md references make targets that do not exist: {sorted(unknown)}"
