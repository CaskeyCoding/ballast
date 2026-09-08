"""CORE-3: ClaudeClient parses responses, retries transient errors, raises terminally."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ballast.core.llm import ClaudeClient, LLMClient, LLMError, LLMResponse


class RateLimitError(Exception):
    """Stands in for anthropic.RateLimitError (matched by class name)."""


def _fake_raw(text: str, model: str = "claude-test") -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        model=model,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        stop_reason="end_turn",
    )


class _ScriptedSDK:
    """A fake anthropic client whose .messages.create follows a scripted outcome list."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **_: Any) -> Any:
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes: list[Any], **kw: Any) -> ClaudeClient:
    sdk = _ScriptedSDK(outcomes)
    client = ClaudeClient("sk-test", client_factory=lambda _key: sdk, sleep=lambda _s: None, **kw)
    client._sdk = sdk  # type: ignore[attr-defined]  # expose for assertions
    return client


def test_claude_client_satisfies_protocol() -> None:
    assert isinstance(_client([_fake_raw("hi")]), LLMClient)


def test_parses_text_and_usage() -> None:
    client = _client([_fake_raw("grounded answer", model="claude-x")])
    resp = client.complete([{"role": "user", "content": "q"}], model="claude-x")
    assert isinstance(resp, LLMResponse)
    assert resp.text == "grounded answer"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 7
    assert resp.model == "claude-x"


def test_retries_transient_then_succeeds() -> None:
    client = _client([RateLimitError("slow down"), _fake_raw("ok")])
    resp = client.complete([{"role": "user", "content": "q"}], model="m")
    assert resp.text == "ok"
    assert client._sdk.calls == 2  # type: ignore[attr-defined]


def test_terminal_failure_raises_llmerror() -> None:
    client = _client([RateLimitError("x")] * 10, max_retries=2)
    with pytest.raises(LLMError, match="completion failed"):
        client.complete([{"role": "user", "content": "q"}], model="m")
    assert client._sdk.calls == 3  # type: ignore[attr-defined]  # initial + 2 retries


def test_non_transient_error_is_not_retried() -> None:
    client = _client([ValueError("bad request"), _fake_raw("never reached")])
    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "q"}], model="m")
    assert client._sdk.calls == 1  # type: ignore[attr-defined]
