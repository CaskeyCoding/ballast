"""RAG-7: multi-query unions reformulations; HyDE embeds a hypothetical answer."""

from __future__ import annotations

from ballast.core.chunk import Chunk
from ballast.core.config import ModelRegistry
from ballast.core.embed import HashingEmbedder
from ballast.core.retrieve import RetrieverLike
from ballast.core.store import InMemoryVectorStore, Retrieved
from ballast.core.testing import FakeLLMClient
from ballast.rag.transform import HyDERetriever, MultiQueryRetriever


def _ret(cid: str, score: float) -> Retrieved:
    return Retrieved(chunk=Chunk(cid, "s", "u", "t", "h", cid), score=score)


class _FakeBase:
    """A RetrieverLike that returns scripted results per query string."""

    def __init__(self, by_query: dict[str, list[Retrieved]]) -> None:
        self.by_query = by_query

    def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        return self.by_query.get(query, [])


def test_multi_query_unions_reformulations() -> None:
    base = _FakeBase(
        {
            "orig": [_ret("a", 0.5)],
            "reform1": [_ret("b", 0.9)],
            "reform2": [_ret("a", 0.7), _ret("c", 0.3)],
        }
    )
    client = FakeLLMClient(['{"queries": ["reform1", "reform2"]}'])
    mq = MultiQueryRetriever(base, client, ModelRegistry(), n=2)
    out = mq.retrieve("orig", k=3)
    ids = [r.chunk.chunk_id for r in out]
    # union across all three queries; "a" keeps its best score (0.7), ranked by score desc
    assert set(ids) == {"a", "b", "c"}
    assert ids[0] == "b"  # highest score 0.9
    assert isinstance(mq, RetrieverLike)


def test_hyde_embeds_hypothetical_answer() -> None:
    emb = HashingEmbedder()
    store = InMemoryVectorStore()
    docs = {"comp#0": "compound interest grows over time", "div#0": "diversification spreads risk"}
    store.upsert([(Chunk(t, "s", "u", "t", "h", cid), emb.embed(t)) for cid, t in docs.items()])
    # the hypothetical answer mentions compounding, so it should retrieve comp#0
    client = FakeLLMClient(["Compound interest grows your money over time as interest compounds."])
    hyde = HyDERetriever(store, emb, client, ModelRegistry())
    out = hyde.retrieve("how does saving grow", k=1)
    assert out[0].chunk.chunk_id == "comp#0"
    assert isinstance(hyde, RetrieverLike)
