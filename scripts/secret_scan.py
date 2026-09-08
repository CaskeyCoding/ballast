#!/usr/bin/env python3
"""Lightweight local secret scan (a gitleaks stand-in with no external dependency).

Scans git-tracked text files for credential patterns and fails with a non-zero exit if any are found.
Wired into scripts/local_ci.py so a committed key surfaces locally (GitHub Actions is not used here).
Test fixtures are allowlisted by their exact synthetic literals (so a real key pasted into a fixture
file still flags); this scanner's own pattern definitions are allowlisted by path.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# label -> compiled pattern. Mirrors gateway/input/secrets.py plus a private-key block.
PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic/openai key": re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

# Known synthetic fixture literals, matched by exact text rather than by file, so a REAL key
# pasted into a fixture file would still be reported. Collected from tests/test_gateway_input.py
# and tests/test_config.py by running PATTERNS over the formerly file-allowlisted paths.
ALLOWED_LITERALS = {
    "sk-ant-abcdefghijklmnopqrstuvwxyz123",
    "sk-from-secrets-manager",
}

# Allowlisted by PATH, not literal: this scanner's own regexes are key-shaped code, not secrets.
PATH_ALLOWLIST = {
    "scripts/secret_scan.py",
}

_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pyc", ".whl"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line.strip()]


def scan_text(text: str) -> list[str]:
    """Labels with at least one match that is not a known synthetic literal."""
    return [
        label
        for label, rx in PATTERNS.items()
        if any(m.group(0) not in ALLOWED_LITERALS for m in rx.finditer(text))
    ]


def scan() -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in PATH_ALLOWLIST or path.suffix in _BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for label in scan_text(text):
            findings.append((rel, label))
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("SECRET SCAN FAILED:")
        for rel, label in findings:
            print(f"  - {rel}: possible {label}")
        return 1
    print("secret scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
