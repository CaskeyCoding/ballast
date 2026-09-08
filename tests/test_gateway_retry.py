"""GW-12: an output-guardrail block triggers one corrected retry before falling back."""

from __future__ import annotations

from ballast.gateway.gateway import Gateway
from ballast.gateway.types import Answer, HookResult, Request


class _NeedsCorrection:
    """Returns a bad answer first; a good one once a correction is supplied."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def __call__(self, q: str, correction: str | None) -> Answer:
        self.calls.append(correction)
        text = "fixed answer" if correction else "bad answer"
        return Answer(text=text, citations=[])


class _BlockBad:
    name = "block-bad"

    def check(self, request: Request, answer: Answer) -> HookResult:
        if "bad" in answer.text:
            return HookResult.block("block-bad", "answer was bad")
        return HookResult.allow()


def test_corrected_retry_recovers() -> None:
    handler = _NeedsCorrection()
    resp = Gateway(handler, post_hooks=[_BlockBad()]).process("q")
    assert resp.blocked is False
    assert resp.answer.text == "fixed answer"
    assert handler.calls == [
        None,
        "A prior answer was rejected (block-bad): answer was bad. Fix it.",
    ]
    assert any(a.action == "retry" for a in resp.audit)


class _AlwaysBad:
    def __call__(self, q: str, correction: str | None) -> Answer:
        return Answer(text="bad answer", citations=[])


def test_still_failing_falls_back_after_one_retry() -> None:
    resp = Gateway(_AlwaysBad(), post_hooks=[_BlockBad()]).process("q")
    assert resp.blocked is True
    assert "withheld" in resp.answer.text
    # exactly one retry attempt was recorded
    assert sum(1 for a in resp.audit if a.action == "retry") == 1
