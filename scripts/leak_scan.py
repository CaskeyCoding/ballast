#!/usr/bin/env python3
"""Local disclosure guard: fail if a forbidden pattern appears in a tracked file.

Scans every git-tracked text file against two pattern layers:

1. Built-in patterns (for example a Windows home-path literal, which would leak a username).
2. Mandatory local-only patterns from `.leak_scan_terms` at the repo root: one regular expression
   per line, `#` comments and blank lines ignored, matched case-insensitively. The file is
   ordinary local configuration and is git-ignored. The scan fails closed when it is absent: a
   run that cannot load the local terms cannot prove the tree clean, so `main()` reports the
   failure and exits non-zero. An explicit `--builtin-only` flag opts into the built-in checks
   alone for local experiments; it is never the default. For each loaded term, common encoded
   forms (base64, hex, rot13) of its plain spellings are also derived at runtime and checked.

Wired into scripts/local_ci.py, so these checks run as a deterministic gate.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_PATH = ROOT / ".leak_scan_terms"

# Patterns that are safe to spell here because the pattern itself discloses nothing.
BUILTIN: dict[str, re.Pattern[str]] = {
    # A Windows home-path literal leaks a username into a public repo.
    "home path (leaks username)": re.compile(r"C:[\\/]Users[\\/]"),
}

_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pyc", ".whl"}

# A bracket character class with an optional quantifier, e.g. `[\s_-]?`: treated as a separator
# when deriving the plain spellings of a term.
_CLASS_RE = re.compile(r"\[[^\]]*\][?*+]?")


def _read_terms(path: Path) -> list[tuple[int, str]] | None:
    if not path.exists():
        return None
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append((lineno, line))
    return lines


def load_private_patterns(path: Path = TERMS_PATH) -> dict[str, re.Pattern[str]] | None:
    """Load the local patterns, or None when the terms file is absent."""
    lines = _read_terms(path)
    if lines is None:
        return None
    return {f"private term (line {n})": re.compile(line, re.I) for n, line in lines}


def _plain_variants(pattern_line: str) -> set[str]:
    """Plain spellings a term pattern can match, for deriving encoded forms.

    A bracket-class separator (e.g. `[\\s_-]?`) is expanded to the common joiners; escapes are
    dropped. A line whose parts are not purely alphanumeric contributes only its literal form.
    """
    core = _CLASS_RE.sub("|", pattern_line).replace("\\", "")
    parts = [p for p in core.split("|") if p]
    if not parts:
        return set()
    if len(parts) == 1 or any(not p.isalnum() for p in parts):
        return {"".join(parts)}
    return {sep.join(parts) for sep in ("", " ", "-", "_", "|")}


def derived_encoded_patterns(path: Path = TERMS_PATH) -> dict[str, re.Pattern[str]]:
    """Encoded forms (base64, hex, rot13) of each loaded term, computed at runtime."""
    lines = _read_terms(path)
    if not lines:
        return {}
    patterns: dict[str, re.Pattern[str]] = {}
    for lineno, line in lines:
        encoded: set[str] = set()
        for variant in _plain_variants(line):
            # Base64 and hex are casing-sensitive (b64 of `foo` and `Foo` differ, and `re.I`
            # cannot recover that), so encode the common casings plus the original spelling.
            # Rot13 keeps letter case, so the original spelling with `re.I` already covers it.
            casings = {variant, variant.lower(), variant.title(), variant.upper()}
            for form in casings:
                encoded.add(base64.b64encode(form.encode()).decode())
                encoded.add(form.encode().hex())
            encoded.add(codecs.encode(variant, "rot13"))
        for i, form in enumerate(sorted(encoded), start=1):
            label = f"encoded private term (line {lineno}, form {i})"
            patterns[label] = re.compile(re.escape(form), re.I)
    return patterns


def all_patterns(
    builtin_only: bool = False, terms_path: Path = TERMS_PATH
) -> dict[str, re.Pattern[str]]:
    patterns = dict(BUILTIN)
    if builtin_only:
        print("leak scan: --builtin-only in effect; local patterns were skipped.")
        return patterns
    private = load_private_patterns(terms_path)
    if private is None:
        print(
            "leak scan WARNING: .leak_scan_terms not found; local patterns were skipped. "
            "Built-in checks still ran."
        )
    else:
        patterns.update(private)
        patterns.update(derived_encoded_patterns(terms_path))
    return patterns


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line.strip()]


def tracked_but_ignored(cwd: Path = ROOT) -> list[str]:
    """Paths that git tracks but .gitignore also ignores (e.g. a force-added file).

    A force-added ignored file is exactly the class that would carry the terms file or
    `proposals/` into a snapshot, so it is a hard failure.
    """
    listing = subprocess.run(
        ["git", "ls-files"], cwd=cwd, capture_output=True, text=True, check=True
    )
    check = subprocess.run(
        # --no-index: by default check-ignore skips indexed paths, which would hide exactly
        # the force-added files this check exists to catch. Bytes in/out: text mode would
        # rewrite \n to \r\n on the stdin pipe and corrupt the paths.
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=cwd,
        input=listing.stdout.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if check.returncode not in (0, 1):  # 0: some ignored; 1: none ignored
        raise RuntimeError(f"git check-ignore failed: {check.stderr.decode('utf-8').strip()}")
    return sorted(line for line in check.stdout.decode("utf-8").splitlines() if line.strip())


def scan_text(text: str, patterns: dict[str, re.Pattern[str]] | None = None) -> list[str]:
    if patterns is None:
        patterns = all_patterns()
    return [label for label, rx in patterns.items() if rx.search(text)]


def scan(patterns: dict[str, re.Pattern[str]] | None = None) -> list[tuple[str, str]]:
    if patterns is None:
        patterns = all_patterns()
    findings: list[tuple[str, str]] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix in _BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for label in scan_text(text, patterns):
            findings.append((rel, label))
    return findings


def main(argv: list[str] | None = None, terms_path: Path = TERMS_PATH) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--builtin-only",
        action="store_true",
        help="run the built-in checks only (local experiments; never the default)",
    )
    args = parser.parse_args(argv)
    if not args.builtin_only and load_private_patterns(terms_path) is None:
        print(
            "LEAK SCAN FAILED: .leak_scan_terms is missing; " "the scan cannot prove the tree clean"
        )
        return 2
    findings = scan(all_patterns(builtin_only=args.builtin_only, terms_path=terms_path))
    if findings:
        print("LEAK SCAN FAILED (forbidden pattern in a tracked file):")
        for rel, label in findings:
            print(f"  - {rel}: {label}")
        return 1
    for path in tracked_but_ignored():
        print(f"LEAK SCAN FAILED (tracked file is gitignored): {path}")
        return 1
    print("leak scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
