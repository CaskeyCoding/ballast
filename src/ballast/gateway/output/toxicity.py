"""Output toxicity screen (GW-7): replace a toxic answer with the safe fallback.

A published assistant must not emit toxic content even if the corpus or a jailbreak induces it. Only
substantive answers are screened; an explicit refusal is skipped, so the classifier is not spent on
the fallback text.
"""

from __future__ import annotations

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.structured import complete_structured
from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.types import Answer, HookResult, Request


class ToxicityVerdict(BaseModel):
    toxic: bool
    reason: str


class ToxicityGuard:
    name = "toxicity"

    def __init__(self, client: LLMClient, registry: ModelRegistry) -> None:
        self._client = client
        self._registry = registry

    def check(self, request: Request, answer: Answer) -> HookResult:
        text = answer.text.strip()
        if not text or text == INSUFFICIENT:
            return HookResult.allow()  # nothing substantive to screen
        verdict = complete_structured(
            self._client,
            [{"role": "user", "content": answer.text}],
            ToxicityVerdict,
            model=self._registry.resolve("classifier"),
            system=(
                "Decide whether the text contains toxic, hateful, harassing, or otherwise unsafe "
                'content. Return JSON {"toxic": bool, "reason": str}. Ordinary text is not toxic.'
            ),
        )
        if verdict.toxic:
            return HookResult.block("toxicity", verdict.reason)
        return HookResult.allow()
