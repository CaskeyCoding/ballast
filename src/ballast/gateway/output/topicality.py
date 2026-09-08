"""Output topicality check (GW-8): keep answers on the finance/investing domain.

An on-topic assistant is part of the policy promise and shrinks a jailbreak's blast radius. Only
substantive answers are checked; a refusal is skipped so the classifier is not spent on it.
"""

from __future__ import annotations

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.structured import complete_structured
from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.types import Answer, HookResult, Request


class TopicalityVerdict(BaseModel):
    on_topic: bool
    reason: str


class TopicalityGuard:
    name = "topicality"

    def __init__(self, client: LLMClient, registry: ModelRegistry) -> None:
        self._client = client
        self._registry = registry

    def check(self, request: Request, answer: Answer) -> HookResult:
        text = answer.text.strip()
        if not text or text == INSUFFICIENT:
            return HookResult.allow()
        verdict = complete_structured(
            self._client,
            [{"role": "user", "content": answer.text}],
            TopicalityVerdict,
            model=self._registry.resolve("classifier"),
            system=(
                "Decide whether the text is about personal finance or investing. Return JSON "
                '{"on_topic": bool, "reason": str}. Off-domain content is not on_topic.'
            ),
        )
        if not verdict.on_topic:
            return HookResult.block("topicality", verdict.reason)
        return HookResult.allow()
