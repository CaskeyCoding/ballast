"""RAG-9: token streaming (Claude + Fake) and node-event streaming from the graph."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.ingest import CORPUS_DIR, build_index
from ballast.core.llm import ClaudeClient, StreamingClient
from ballast.core.retrieve import Retriever
from ballast.core.testing import FakeLLMClient
from ballast.core.trace import Trace
from ballast.rag.graph import build_baseline_graph
from ballast.rag.stream import iter_node_events


def test_fake_streams_chunks_reassembling_to_text() -> None:
    fake = FakeLLMClient(["compound interest grows over time"])
    assert isinstance(fake, StreamingClient)
    chunks = list(fake.stream([{"role": "user", "content": "q"}], model="m"))
    assert len(chunks) > 1  # streamed in pieces
    assert "".join(chunks) == "compound interest grows over time"


class _StreamCM:
    def __init__(self, chunks: list[str]) -> None:
        self.text_stream = iter(chunks)

    def __enter__(self) -> _StreamCM:
        return self

    def __exit__(self, *_: Any) -> bool:
        return False


def test_claude_client_streams() -> None:
    sdk = SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: _StreamCM(["Hel", "lo"])))
    client = ClaudeClient("k", client_factory=lambda _key: sdk)
    assert isinstance(client, StreamingClient)
    assert "".join(client.stream([{"role": "user", "content": "q"}], model="m")) == "Hello"


def test_node_event_stream_lists_nodes_in_order() -> None:
    emb = HashingEmbedder()
    retriever = Retriever(store=build_index(CORPUS_DIR, emb), embedder=emb)
    graph = build_baseline_graph(
        retriever, FakeLLMClient(["an answer [1]"]), ModelRegistry(), Trace("t")
    )
    events = list(iter_node_events(graph, {"question": "what is diversification", "retries": 0}))
    assert events == ["retrieve", "generate"]
