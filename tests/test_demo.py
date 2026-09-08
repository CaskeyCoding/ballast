"""DX-3: each demo question reaches its intended path on the seed corpus.

Per scenario the test injects a FakeLLMClient tuned to drive that path deterministically: the block
needs no model call (the heuristic stops it), the cited answer passes the critic on the first try,
and the self-heal scenario scripts a critic rejection followed by a passing retry.
"""

from __future__ import annotations

from collections.abc import Sequence

from examples.demo import Scenario, run_demo

from ballast.core.config import Settings
from ballast.core.llm import Message
from ballast.core.testing import FakeLLMClient


def _content(messages: Sequence[Message]) -> str:
    return " ".join(str(m.get("content", "")) for m in messages)


_GRADE_KEEP = '{"relevant_indices": [0]}'
_CRITIC_PASS = '{"grounded": true, "relevant": true, "reason": "supported by the sources"}'
_CRITIC_FAIL = '{"grounded": false, "relevant": true, "reason": "sources do not support this"}'
_ANSWER = "Diversification spreads money across many investments so one loss is not ruinous."


def _client_for(sc: Scenario) -> FakeLLMClient:
    if sc.intended == "block":
        return FakeLLMClient([])  # blocked at the gateway; the client must never be called
    if sc.intended == "cited":
        return FakeLLMClient(
            rules=[
                (lambda m: "Chunks:" in _content(m), _GRADE_KEEP),
                (lambda m: "Answer:" in _content(m), _CRITIC_PASS),
            ],
            default=_ANSWER,
        )
    # self_heal: grade, generate, critic(fail) -> rewrite -> grade, generate, critic(pass)
    return FakeLLMClient(
        [
            _GRADE_KEEP,
            "A first answer the critic will reject.",
            _CRITIC_FAIL,
            "a rewritten, sharper question",
            _GRADE_KEEP,
            _ANSWER,
            _CRITIC_PASS,
        ]
    )


def test_each_demo_question_reaches_its_intended_path() -> None:
    settings = Settings(embedder="hashing")  # no torch, deterministic, offline
    results = run_demo(client_factory=_client_for, settings=settings)
    by_intent = {sc.intended: path for sc, path in results}

    assert by_intent["block"] == "block"
    assert by_intent["self_heal"] == "self_heal"
    assert by_intent["cited"] == "cited"


def test_block_scenario_makes_no_model_call() -> None:
    settings = Settings(embedder="hashing")
    seen: dict[str, FakeLLMClient] = {}

    def factory(sc: Scenario) -> FakeLLMClient:
        client = _client_for(sc)
        seen[sc.intended] = client
        return client

    run_demo(client_factory=factory, settings=settings)
    assert seen["block"].calls == []  # the injection heuristic short-circuits before the handler
