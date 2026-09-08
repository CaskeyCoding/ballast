"""RAG-14: mermaid export and sample run state log."""

from __future__ import annotations

from ballast.rag.viz import _build_graph, export_mermaid, sample_run_states


def test_mermaid_contains_all_nodes() -> None:
    mermaid = export_mermaid(_build_graph())
    for node in ("retrieve", "grade_documents", "generate", "critic", "rewrite_query", "fallback"):
        assert node in mermaid


def test_sample_run_states_records_nodes() -> None:
    events = sample_run_states(
        _build_graph(), {"question": "what is diversification", "retries": 0}
    )
    nodes = [e["node"] for e in events]
    assert nodes[:3] == ["retrieve", "grade_documents", "generate"]
    # the generate event carries the answer text
    gen = next(e for e in events if e["node"] == "generate")
    assert gen["answer"].startswith("Diversification")
