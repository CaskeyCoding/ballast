"""GW-8: the topicality guard blocks off-domain answers and skips refusals."""

from __future__ import annotations

from ballast.core.config import ModelRegistry
from ballast.core.testing import FakeLLMClient
from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.output.topicality import TopicalityGuard
from ballast.gateway.types import Answer, Request

_REQ = Request("q")


def test_off_topic_answer_blocked() -> None:
    client = FakeLLMClient(['{"on_topic": false, "reason": "about cooking"}'])
    res = TopicalityGuard(client, ModelRegistry()).check(_REQ, Answer("bake bread at 220C", []))
    assert res.action == "block" and res.rule == "topicality"


def test_on_topic_answer_allowed() -> None:
    client = FakeLLMClient(['{"on_topic": true, "reason": "investing"}'])
    res = TopicalityGuard(client, ModelRegistry()).check(
        _REQ, Answer("diversify across assets", [])
    )
    assert res.action == "allow"
    assert len(client.calls) == 1


def test_refusal_skips_the_model() -> None:
    client = FakeLLMClient([])  # would raise if called
    res = TopicalityGuard(client, ModelRegistry()).check(_REQ, Answer(INSUFFICIENT, []))
    assert res.action == "allow"
    assert client.calls == []
