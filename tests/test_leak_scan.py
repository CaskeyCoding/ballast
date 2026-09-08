"""SEC: the leak scanner flags forbidden patterns and the tracked repo is clean.

Local patterns come from a git-ignored config file (`.leak_scan_terms`). These tests exercise the
mechanism with stand-in patterns; the live-tree test runs whatever patterns the local machine
actually has loaded.
"""

from __future__ import annotations

import base64
import codecs
import re
import subprocess
from pathlib import Path

from scripts.leak_scan import (
    BUILTIN,
    _plain_variants,
    derived_encoded_patterns,
    load_private_patterns,
    main,
    scan,
    scan_text,
    tracked_but_ignored,
)

_STAND_IN = {"private term (line 1)": re.compile(r"secret[\s_-]?codename", re.I)}


def test_flags_private_term() -> None:
    assert scan_text("see the secretcodename docs", _STAND_IN) == ["private term (line 1)"]


def test_flags_private_term_with_separators() -> None:
    assert scan_text("the secret codename product", _STAND_IN) == ["private term (line 1)"]
    assert scan_text("a Secret-Codename reference", _STAND_IN) == ["private term (line 1)"]


def test_load_private_patterns_parses_file(tmp_path: Path) -> None:
    terms = tmp_path / ".leak_scan_terms"
    terms.write_text("# comment\n\nsecret[\\s_-]?codename\n", encoding="utf-8")
    patterns = load_private_patterns(terms)
    assert patterns is not None
    assert list(patterns) == ["private term (line 3)"]
    assert patterns["private term (line 3)"].search("Secret Codename")


def test_load_private_patterns_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_private_patterns(tmp_path / "absent") is None


def test_plain_variants_expands_separator_class() -> None:
    assert _plain_variants(r"secret[\s_-]?codename") == {
        "secretcodename",
        "secret codename",
        "secret-codename",
        "secret_codename",
        "secret|codename",
    }


def test_plain_variants_literal_line_is_single_form() -> None:
    assert _plain_variants(r"someone@example\.com") == {"someone@example.com"}


def test_derived_encodings_flag_encoded_forms(tmp_path: Path) -> None:
    terms = tmp_path / ".leak_scan_terms"
    terms.write_text("secret[\\s_-]?codename\n", encoding="utf-8")
    patterns = derived_encoded_patterns(terms)
    for form in (
        base64.b64encode(b"secretcodename").decode(),
        b"secretcodename".hex(),
        codecs.encode("secret codename", "rot13"),
    ):
        assert scan_text(f"blob: {form} end", patterns), f"missed encoded form {form!r}"


def test_derived_encodings_missing_file_is_empty(tmp_path: Path) -> None:
    assert derived_encoded_patterns(tmp_path / "absent") == {}


def test_derived_encodings_cover_other_casings(tmp_path: Path) -> None:
    # Base64/hex are casing-sensitive, so Title/UPPER casings of a term are derived too.
    terms = tmp_path / ".leak_scan_terms"
    terms.write_text("zzzfakezzz\n", encoding="utf-8")
    patterns = derived_encoded_patterns(terms)
    for form in (
        base64.b64encode(b"Zzzfakezzz").decode(),
        base64.b64encode(b"ZZZFAKEZZZ").decode(),
        b"Zzzfakezzz".hex(),
    ):
        assert scan_text(f"blob: {form} end", patterns), f"missed encoded form {form!r}"


def test_flags_home_path_username() -> None:
    sep = "\\"  # build the path at runtime so this source has no literal home path
    sample = "see " + "C:" + sep + "Users" + sep + "alice" + sep + "notes.txt"
    assert "home path (leaks username)" in scan_text(sample, BUILTIN)


def test_clean_text_passes() -> None:
    assert scan_text("ordinary education about investing and diversification", BUILTIN) == []


def test_repo_is_clean() -> None:
    # The live scan over git-tracked files must be clean before the repo goes public. It uses the
    # local patterns (and their derived encoded forms) when present and degrades to the built-in
    # checks when they are absent.
    assert scan() == []


def test_main_fails_closed_without_terms_file(tmp_path: Path) -> None:
    # A missing terms file is a hard failure: the scan cannot prove the tree clean.
    assert main([], terms_path=tmp_path / "absent") != 0


def test_main_builtin_only_returns_zero_on_clean_tree(tmp_path: Path) -> None:
    # --builtin-only opts out of the local terms for local experiments; the stand-in terms file
    # holds an obviously fake term and is ignored in this mode.
    terms = tmp_path / ".leak_scan_terms"
    terms.write_text("zzz-fake-term\n", encoding="utf-8")
    assert main(["--builtin-only"], terms_path=terms) == 0


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")


def test_tracked_but_ignored_flags_force_added_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("force-added anyway\n", encoding="utf-8")
    (tmp_path / "clean.txt").write_text("ordinary\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", "clean.txt")
    _git(tmp_path, "add", "-f", "ignored.txt")
    assert tracked_but_ignored(cwd=tmp_path) == ["ignored.txt"]


def test_tracked_but_ignored_clean_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "clean.txt").write_text("ordinary\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", "clean.txt")
    assert tracked_but_ignored(cwd=tmp_path) == []
