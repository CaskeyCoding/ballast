"""OBS-2: the trace viewer renders nodes, calls, decisions, and totals."""

from __future__ import annotations

from pathlib import Path

from ballast.core.cost import CostMeter
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import MeteredClient, Trace
from ballast.obs.store import save_trace
from ballast.obs.viewer import render_trace


def test_render_contains_nodes_decisions_calls_totals() -> None:
    trace = Trace(run_id="r1")
    trace.record_node("retrieve", "3 chunks")
    trace.record_decision("critic", "pass", "supported")
    MeteredClient(FakeLLMClient(["hi"]), CostMeter(1.0), trace).complete(
        [{"role": "user", "content": "q"}], model="claude-haiku-4-5-20251001"
    )

    out = render_trace(trace.to_dict())
    assert "run r1" in out
    assert "retrieve - 3 chunks" in out
    assert "[critic] pass: supported" in out
    assert "tok" in out and "totals:" in out


def test_viewer_loads_a_saved_trace(tmp_path: Path) -> None:
    trace = Trace(run_id="saved")
    trace.record_node("generate", "ok")
    save_trace(trace, runs_dir=tmp_path)
    from ballast.obs.store import load_trace

    out = render_trace(load_trace("saved", runs_dir=tmp_path))
    assert "generate - ok" in out
