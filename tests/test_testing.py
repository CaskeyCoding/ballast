"""CORE-5: FakeLLMClient scripted and rule-based behavior."""

from __future__ import annotations

import pytest

from ballast.core.llm import LLMClient
from ballast.core.testing import FakeLLMClient


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeLLMClient(["x"]), LLMClient)


def test_scripted_returns_in_order() -> None:
    fake = FakeLLMClient(["first", "second"])
    assert fake.complete([{"role": "user", "content": "a"}], model="m").text == "first"
    assert fake.complete([{"role": "user", "content": "b"}], model="m").text == "second"


def test_records_calls_and_estimates_tokens() -> None:
    fake = FakeLLMClient(["hello world"])
    resp = fake.complete([{"role": "user", "content": "question here"}], model="m", system="sys")
    assert fake.calls[0]["model"] == "m"
    assert resp.input_tokens >= 1 and resp.output_tokens >= 1


def test_rules_match_then_default() -> None:
    fake = FakeLLMClient(
        rules=[(lambda msgs: "grade" in msgs[-1]["content"], "GRADED")],
        default="FALLBACK",
    )
    assert fake.complete([{"role": "user", "content": "please grade"}], model="m").text == "GRADED"
    assert fake.complete([{"role": "user", "content": "other"}], model="m").text == "FALLBACK"


def test_exhausted_raises() -> None:
    fake = FakeLLMClient(["only one"])
    fake.complete([{"role": "user", "content": "a"}], model="m")
    with pytest.raises(AssertionError, match="exhausted"):
        fake.complete([{"role": "user", "content": "b"}], model="m")
