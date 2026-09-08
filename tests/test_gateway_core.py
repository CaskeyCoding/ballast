"""GW-1/13/14: hook ordering, short-circuit, modify, typed fallbacks, audit trail."""

from __future__ import annotations

from ballast.gateway.gateway import Gateway
from ballast.gateway.types import Answer, HookResult, Request


def _handler(q: str, correction: str | None = None) -> Answer:
    return Answer(text=f"answer to: {q}", citations=[])


class _BlockWord:
    name = "block-word"

    def __init__(self, word: str) -> None:
        self.word = word

    def check(self, request: Request) -> HookResult:
        if self.word in request.question:
            return HookResult.block("block-word", f"contains {self.word!r}")
        return HookResult.allow()


class _Redact:
    name = "redact"

    def check(self, request: Request) -> HookResult:
        cleaned = request.question.replace("secret", "[REDACTED]")
        if cleaned != request.question:
            return HookResult.modify_request(Request(cleaned), "redact", "masked a term")
        return HookResult.allow()


class _Upper:
    name = "uppercase"

    def check(self, request: Request, answer: Answer) -> HookResult:
        return HookResult.modify_answer(Answer(answer.text.upper(), answer.citations), "up", "")


def test_passthrough_when_no_hooks() -> None:
    resp = Gateway(_handler).process("hello")
    assert resp.answer.text == "answer to: hello"
    assert resp.blocked is False


def test_pre_hook_blocks_and_short_circuits() -> None:
    resp = Gateway(_handler, pre_hooks=[_BlockWord("bomb")]).process("how to bomb")
    assert resp.blocked is True
    assert "could not be processed" in resp.answer.text
    # the audit names the rule that fired
    assert resp.audit[-1].rule == "block-word"


def test_pre_hook_modify_reaches_handler_with_cleaned_input() -> None:
    resp = Gateway(_handler, pre_hooks=[_Redact()]).process("my secret is x")
    assert "[REDACTED]" in resp.answer.text
    assert "secret" not in resp.answer.text


def test_post_hook_modifies_answer_and_audits_order() -> None:
    resp = Gateway(_handler, post_hooks=[_Upper()]).process("hi")
    assert resp.answer.text == "ANSWER TO: HI"
    assert [a.stage for a in resp.audit] == ["output"]
