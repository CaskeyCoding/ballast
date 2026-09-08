"""SEC-1: the secret scanner flags planted credentials and the repo is clean."""

from __future__ import annotations

from scripts.secret_scan import ALLOWED_LITERALS, PATH_ALLOWLIST, scan, scan_text

# Built by concatenation so this file never contains a literal key-shaped string.
_FAKE_KEY = "sk-" + "ant-" + "A" * 30
_FAKE_AWS = "AKIA" + "1234567890ABCDEF"


def test_flags_planted_api_key() -> None:
    assert scan_text(f"my key is {_FAKE_KEY}") == ["anthropic/openai key"]


def test_flags_planted_aws_key() -> None:
    assert "aws access key" in scan_text(f"creds {_FAKE_AWS}")


def test_clean_text_passes() -> None:
    assert scan_text("this is ordinary code with no secrets in it") == []


def test_allowed_literals_do_not_flag() -> None:
    for literal in ALLOWED_LITERALS:
        assert scan_text(f"fixture value: {literal}") == []


def test_unknown_key_in_fixture_like_text_flags() -> None:
    # A key that is NOT a known synthetic literal flags even in fixture-shaped text.
    unknown = "sk-" + "z" * 25
    assert unknown not in ALLOWED_LITERALS
    assert scan_text(f'return "{unknown}"') == ["anthropic/openai key"]


def test_former_file_allowlist_is_gone() -> None:
    # Formerly allowlisted files are now scanned; only the scanner itself is skipped by path
    # (its own regexes are key-shaped code, not secrets).
    assert PATH_ALLOWLIST == {"scripts/secret_scan.py"}


def test_repo_has_no_committed_secrets() -> None:
    # The live scan over git-tracked files must be clean (allowed literals cover fixtures).
    assert scan() == []
