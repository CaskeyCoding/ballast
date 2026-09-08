"""The gateway: run ordered pre-hooks, the handler, then post-hooks, with short-circuit and audit.

`Gateway` wraps any `question -> Answer` handler (the RAG). Each guardrail is a hook; a hook can
allow, block (short-circuit to a typed fallback), or modify the request/answer. Every decision is
recorded in an audit trail so you can see what was blocked, redacted, or rewritten and which rule.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ballast.gateway import fallback
from ballast.gateway.types import Answer, HookResult, Request


class PreHook(Protocol):
    name: str

    def check(self, request: Request) -> HookResult: ...


class PostHook(Protocol):
    name: str

    def check(self, request: Request, answer: Answer) -> HookResult: ...


@dataclass
class AuditEntry:
    stage: str  # "input" | "output"
    hook: str
    action: str
    rule: str = ""
    reason: str = ""


@dataclass
class GatewayResponse:
    answer: Answer
    blocked: bool
    audit: list[AuditEntry] = field(default_factory=list)


# handler: (question, correction) -> Answer. correction is None on the first attempt; on an output
# guardrail block the gateway retries once with the failing rule's message (GW-12).
Handler = Callable[[str, str | None], Answer]


class Gateway:
    def __init__(
        self,
        handler: Handler,
        *,
        pre_hooks: Sequence[PreHook] = (),
        post_hooks: Sequence[PostHook] = (),
    ) -> None:
        self._handler = handler
        self._pre = list(pre_hooks)
        self._post = list(post_hooks)

    def _run_post(
        self, request: Request, answer: Answer, audit: list[AuditEntry]
    ) -> tuple[Answer, HookResult | None]:
        """Run post-hooks; return the (possibly modified) answer and the first blocking result."""
        for post in self._post:
            result = post.check(request, answer)
            audit.append(AuditEntry("output", post.name, result.action, result.rule, result.reason))
            if result.action == "block":
                return answer, result
            if result.action == "modify" and result.answer is not None:
                answer = result.answer
        return answer, None

    def process(self, question: str) -> GatewayResponse:
        audit: list[AuditEntry] = []
        request = Request(question=question)

        for pre in self._pre:
            result = pre.check(request)
            audit.append(AuditEntry("input", pre.name, result.action, result.rule, result.reason))
            if result.action == "block":
                return GatewayResponse(fallback.blocked_input(result.reason), True, audit)
            if result.action == "modify" and result.request is not None:
                request = result.request

        answer = self._handler(request.question, None)
        answer, blocked = self._run_post(request, answer, audit)

        if blocked is not None:
            # GW-12: one corrected retry before falling back.
            correction = f"A prior answer was rejected ({blocked.rule}): {blocked.reason}. Fix it."
            audit.append(AuditEntry("output", "auto-retry", "retry", blocked.rule, correction))
            answer = self._handler(request.question, correction)
            answer, blocked = self._run_post(request, answer, audit)

        if blocked is not None:
            return GatewayResponse(fallback.blocked_output(blocked.reason), True, audit)
        return GatewayResponse(answer, False, audit)
