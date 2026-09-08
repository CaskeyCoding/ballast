"""Personalized-advice solicitation guard (EVAL-23), two-tier like the injection classifier.

Adversarial advice asks ("Should I buy I-bonds right now?") carry no injection vocabulary, so
neither injection layer ever sees them, and the RAG answers them faithfully from the corpus in an
educational tone that the output policy's blunt-phrase regexes never match. This input guard closes
that hole: a cheap high-recall heuristic spots advice-seeking language, and only those inputs
escalate to a bounded classifier that separates a PERSONALIZED decision ask (their money, their
situation) from a general educational question. Education passes; solicitation is blocked.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.structured import complete_structured
from ballast.gateway.types import HookResult, Request

# Mirrors the policy rule's message so input- and output-layer blocks read the same to the user.
EDUCATION_NOT_ADVICE = "this assistant gives general education, not personalized financial advice"

# Low-precision, high-recall trigger: first-person decision asks and pick-me-a-winner phrasings
# escalate to the classifier; anything else is allowed with no model call, so cost stays bounded.
_ADVICE = re.compile(
    r"\bshould (i|we)\b"
    r"|\badvise me\b"
    r"|\b(personalized|personal) (financial |investment )?advice\b"
    r"|\bmy (portfolio|money|savings|investments?|retirement|ira|401k"
    r"|accounts?|loans?|debts?|situation)\b"
    r"|\brecommend\b.{0,40}\b(stocks?|etfs?|funds?|bonds?|tickers?|buy|sell|invest)\b"
    r"|\bwhich (stock|etf|fund|bond|ticker)s?\b.{0,60}\b(buy|pick|choose|invest|beat)\b"
    r"|\btell me (what|which) to (buy|sell)\b"
    r"|\bwhat\b.{0,30}\bshould\b.{0,20}\b(buy|sell|invest)\b",
    re.I,
)


class AdviceVerdict(BaseModel):
    solicitation: bool
    reason: str


class AdviceSolicitationGuard:
    name = "advice-solicitation"

    def __init__(self, client: LLMClient, registry: ModelRegistry) -> None:
        self._client = client
        self._registry = registry

    def check(self, request: Request) -> HookResult:
        if not _ADVICE.search(request.question):
            return HookResult.allow()  # clearly educational: no model call, no cost
        verdict = complete_structured(
            self._client,
            [{"role": "user", "content": request.question}],
            AdviceVerdict,
            model=self._registry.resolve("classifier"),
            system=(
                "Decide whether the user is SOLICITING PERSONALIZED financial advice: asking for "
                "a decision or recommendation about THEIR OWN money, portfolio, or situation "
                "(what they should buy, sell, hold, pay off, or allocate, or which investment "
                "will win for them). A general educational question about how a concept, product, "
                "or method works is not solicitation. "
                'Return JSON {"solicitation": bool, "reason": str}.'
            ),
        )
        if verdict.solicitation:
            return HookResult.block("advice-solicitation", EDUCATION_NOT_ADVICE)
        return HookResult.allow()
