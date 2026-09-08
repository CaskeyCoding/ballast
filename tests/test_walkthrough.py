"""DX-2: the example walkthrough runs end-to-end against the seed corpus with no API key.

Drives examples/walkthrough.py with a rule-based FakeLLMClient (so the grade/generate/critic nodes
resolve deterministically) and the dependency-light hashing embedder, so the whole ingest -> ask ->
trace flow runs offline.
"""

from __future__ import annotations

from collections.abc import Sequence

from examples.walkthrough import run_walkthrough

from ballast.core.config import Settings
from ballast.core.llm import Message
from ballast.core.testing import FakeLLMClient


def _content(messages: Sequence[Message]) -> str:
    return " ".join(str(m.get("content", "")) for m in messages)


def _walkthrough_client() -> FakeLLMClient:
    # Route by the distinguishing text in each node's user message.
    return FakeLLMClient(
        rules=[
            (lambda m: "Chunks:" in _content(m), '{"relevant_indices": [0]}'),
            (
                lambda m: "Answer:" in _content(m),
                '{"grounded": true, "relevant": true, "reason": "supported by the sources"}',
            ),
        ],
        default="Diversification spreads money across many investments so one loss is not ruinous.",
    )


def test_walkthrough_runs_end_to_end(capsys) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(embedder="hashing")  # no torch, deterministic, offline
    trace = run_walkthrough(
        "What is diversification?", client=_walkthrough_client(), settings=settings
    )

    out = capsys.readouterr().out
    assert "[1/3] ingest" in out
    assert "[2/3] ask" in out
    assert "[3/3] trace" in out
    # the trace recorded the pipeline's work and at least one metered call
    node_names = {n["name"] for n in trace.to_dict()["nodes"]}
    assert "retrieve" in node_names and "generate" in node_names
    assert trace.total_tokens > 0
