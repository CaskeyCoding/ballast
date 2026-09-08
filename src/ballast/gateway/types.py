"""Shared gateway contracts: the request/answer envelope and the hook result.

A hook returns a `HookResult` that either allows the message through, blocks it (short-circuiting
to a safe fallback), or modifies it (a redacted request, or a corrected answer). This one small type
lets pre-hooks and post-hooks compose in an ordered pipeline without each knowing about the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Action = Literal["allow", "block", "modify"]


@dataclass
class Request:
    question: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Answer:
    text: str
    citations: list[dict[str, str]] = field(default_factory=list)


@dataclass
class HookResult:
    action: Action
    rule: str = ""
    reason: str = ""
    request: Request | None = None  # set when action == modify on a pre-hook
    answer: Answer | None = None  # set when action == modify on a post-hook

    @classmethod
    def allow(cls) -> HookResult:
        return cls(action="allow")

    @classmethod
    def block(cls, rule: str, reason: str) -> HookResult:
        return cls(action="block", rule=rule, reason=reason)

    @classmethod
    def modify_request(cls, request: Request, rule: str, reason: str) -> HookResult:
        return cls(action="modify", rule=rule, reason=reason, request=request)

    @classmethod
    def modify_answer(cls, answer: Answer, rule: str, reason: str) -> HookResult:
        return cls(action="modify", rule=rule, reason=reason, answer=answer)
