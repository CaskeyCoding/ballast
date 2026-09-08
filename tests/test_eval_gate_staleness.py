"""The eval gate refuses to ride a stale green ledger entry.

A code change must not pass the gate on metrics measured against an old commit. The gate compares
the newest ledger entry's sha to HEAD and fails beyond a small ancestor window, with a documented
docs-only override env var.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ballast.eval.gate import (
    DEFAULT_MAX_BEHIND,
    STALE_OVERRIDE_ENV,
    _check_staleness,
    commits_behind,
    staleness_failure,
)

_ROOT = Path(__file__).resolve().parents[1]


def _rev(spec: str) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", spec], cwd=_ROOT, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def test_fresh_entry_is_not_stale() -> None:
    assert staleness_failure("abc1234", behind=0, max_behind=DEFAULT_MAX_BEHIND) is None


def test_within_window_is_not_stale() -> None:
    assert staleness_failure("abc1234", behind=3, max_behind=3) is None


def test_beyond_window_is_stale() -> None:
    reason = staleness_failure("abc1234", behind=4, max_behind=3)
    assert reason is not None and "4 commits behind" in reason


def test_unknown_sha_is_stale() -> None:
    reason = staleness_failure("abc1234", behind=None, max_behind=3)
    assert reason is not None and "not HEAD or an ancestor" in reason


def test_commits_behind_head_is_zero() -> None:
    assert commits_behind(_rev("HEAD")) == 0


def test_commits_behind_parent_is_one() -> None:
    assert commits_behind(_rev("HEAD~1")) == 1


def test_commits_behind_unknown_sha_is_none() -> None:
    assert commits_behind("unknown") is None
    assert commits_behind("0000000") is None


def test_stale_entry_fails_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STALE_OVERRIDE_ENV, raising=False)
    assert _check_staleness("unknown") == 1


def test_override_env_accepts_stale_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STALE_OVERRIDE_ENV, "1")
    assert _check_staleness("unknown") == 0


def test_max_behind_env_widens_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STALE_OVERRIDE_ENV, raising=False)
    behind = commits_behind(_rev(f"HEAD~{DEFAULT_MAX_BEHIND + 1}"))
    assert behind == DEFAULT_MAX_BEHIND + 1
    assert _check_staleness(_rev(f"HEAD~{DEFAULT_MAX_BEHIND + 1}")) == 1
    monkeypatch.setenv("BALLAST_EVAL_GATE_MAX_BEHIND", str(DEFAULT_MAX_BEHIND + 1))
    assert _check_staleness(_rev(f"HEAD~{DEFAULT_MAX_BEHIND + 1}")) == 0
