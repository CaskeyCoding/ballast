"""GW-7: the toxicity guard blocks toxic answers and skips refusals."""

from __future__ import annotations

from ballast.core.config import ModelRegistry
from ballast.core.testing import FakeLLMClient
from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.output.toxicity import ToxicityGuard
from ballast.gateway.types import Answer, Request

_REQ = Request("q")


def test_toxic_answer_blocked() -> None:
    guard = ToxicityGuard(
        FakeLLMClient(['{"toxic": true, "reason": "harassing content"}']), ModelRegistry()
    )
    res = guard.check(_REQ, Answer("some toxic text", []))
    assert res.action == "block" and res.rule == "toxicity"


def test_clean_answer_allowed() -> None:
    client = FakeLLMClient(['{"toxic": false, "reason": "ordinary"}'])
    res = ToxicityGuard(client, ModelRegistry()).check(
        _REQ, Answer("diversification spreads risk", [])
    )
    assert res.action == "allow"
    assert len(client.calls) == 1


def test_refusal_skips_the_model() -> None:
    client = FakeLLMClient([])  # would raise if called
    res = ToxicityGuard(client, ModelRegistry()).check(_REQ, Answer(INSUFFICIENT, []))
    assert res.action == "allow"
    assert client.calls == []
