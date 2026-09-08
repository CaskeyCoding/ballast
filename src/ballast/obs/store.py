"""Per-run trace store (OBS-1): persist each run's trace to runs/<run_id>.json for inspection.

Debugging a self-heal loop or a guardrail block is far easier from a durable trace than from stdout.
The runs/ directory is gitignored (regenerable exhaust).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ballast.core.trace import Trace

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "runs"


def save_trace(trace: Trace, *, runs_dir: Path = RUNS_DIR) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{trace.run_id}.json"
    path.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    return path


def load_trace(run_id: str, *, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    path = runs_dir / f"{run_id}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
