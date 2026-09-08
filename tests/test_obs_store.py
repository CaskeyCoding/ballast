"""OBS-1: a run's trace persists to runs/<run_id>.json and round-trips."""

from __future__ import annotations

from pathlib import Path

from ballast.core.trace import Trace
from ballast.obs.store import load_trace, save_trace


def test_save_and_load_trace(tmp_path: Path) -> None:
    trace = Trace(run_id="run-xyz")
    trace.record_node("retrieve", "3 chunks")
    trace.record_decision("critic", "pass", "supported")

    path = save_trace(trace, runs_dir=tmp_path)
    assert path.name == "run-xyz.json"

    loaded = load_trace("run-xyz", runs_dir=tmp_path)
    assert loaded["run_id"] == "run-xyz"
    assert loaded["nodes"][0]["name"] == "retrieve"
    assert loaded["decisions"][0]["outcome"] == "pass"
