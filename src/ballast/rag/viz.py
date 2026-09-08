"""Graph visualization (RAG-14): export the compiled topology to mermaid + a sample run state log.

The cyclical self-healing graph is the headline artifact, so this writes `rag/graph.mmd` (shown in
the README) and dumps a sample run's per-node state changes to `rag/sample_run.json` for the docs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_rag_graph
from ballast.rag.state import RAGState

HERE = Path(__file__).resolve().parent
MMD_PATH = HERE / "graph.mmd"
SAMPLE_PATH = HERE / "sample_run.json"

_SCRIPT = [
    '{"relevant_indices": [0]}',
    "Diversification spreads risk across many investments [1].",
    '{"grounded": true, "relevant": true, "reason": "supported"}',
]


def export_mermaid(graph: Any) -> str:
    """Return the mermaid flowchart text of the compiled graph."""
    return str(graph.get_graph().draw_mermaid())


def sample_run_states(graph: Any, state: RAGState) -> list[dict[str, Any]]:
    """Run the graph and record, per node, which state keys it updated (JSON-safe)."""
    events: list[dict[str, Any]] = []
    for event in graph.stream(state):
        for node, update in event.items():
            entry: dict[str, Any] = {"node": node, "updated": sorted(update.keys())}
            if isinstance(update.get("answer"), str):
                entry["answer"] = update["answer"]
            events.append(entry)
    return events


def _build_graph() -> Any:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    client = FakeLLMClient(_SCRIPT)
    return build_rag_graph(retriever, client, ModelRegistry(), Trace("viz"))


def main() -> None:
    MMD_PATH.write_text(export_mermaid(_build_graph()), encoding="utf-8")
    states = sample_run_states(
        _build_graph(), {"question": "what is diversification", "retries": 0}
    )
    SAMPLE_PATH.write_text(json.dumps(states, indent=2), encoding="utf-8")
    print(f"wrote {MMD_PATH.name} and {SAMPLE_PATH.name}")


if __name__ == "__main__":
    main()
