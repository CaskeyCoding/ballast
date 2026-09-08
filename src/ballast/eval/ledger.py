"""EVAL-14 metrics ledger: append each run to a committed JSONL keyed by git SHA.

Regression detection and the trend dashboard both read the history from here, so it is committed and
survives across sessions. Timestamps come from the wall clock at run time.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HISTORY_PATH = REPO_ROOT / "eval" / "history.jsonl"


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def append_entry(
    metrics: dict[str, float],
    *,
    path: Path = HISTORY_PATH,
    sha: str | None = None,
    timestamp: str | None = None,
    intervals: dict[str, list[float]] | None = None,
    n: int | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "sha": sha or git_sha(),
        "timestamp": timestamp or datetime.datetime.now(datetime.UTC).isoformat(),
        "metrics": metrics,
        "intervals": intervals or {},
    }
    if n is not None:
        entry["n"] = n  # golden-set case count: the gate only compares latency like-for-like
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_history(path: Path = HISTORY_PATH) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
