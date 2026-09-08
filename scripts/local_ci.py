#!/usr/bin/env python3
"""Portable local CI gate: scans, lint, type-check, test, and the eval gate.

This is the single source of truth for the merge gate. `make local-ci` calls it, and on
machines without `make` (this Windows box, for one) it runs directly:

    python scripts/local_ci.py

GitHub Actions is not used on this account; this script is the gate. The eval gate step also
fails when the newest eval/history.jsonl entry is stale relative to HEAD; refresh it with
`make eval`, or set BALLAST_EVAL_GATE_ALLOW_STALE=1 for a docs-only change.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each step is (label, argv).
STEPS: list[tuple[str, list[str]]] = [
    ("secret scan", [sys.executable, "scripts/secret_scan.py"]),
    ("leak scan", [sys.executable, "scripts/leak_scan.py"]),
    ("dependency audit", [sys.executable, "scripts/dep_audit.py"]),
    ("ruff check", [sys.executable, "-m", "ruff", "check", "src", "tests"]),
    ("ruff format --check", [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"]),
    ("mypy", [sys.executable, "-m", "mypy"]),
    ("pytest", [sys.executable, "-m", "pytest"]),
    ("eval gate", [sys.executable, "-m", "ballast.eval.gate"]),
]


def main() -> int:
    failures: list[str] = []
    for label, argv in STEPS:
        print(f"\n=== {label} ===", flush=True)
        result = subprocess.run(argv, cwd=ROOT)
        if result.returncode != 0:
            failures.append(label)
    print()
    if failures:
        print(f"local-ci FAILED: {', '.join(failures)}")
        return 1
    print("local-ci PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
