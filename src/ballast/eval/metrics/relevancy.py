"""Answer relevancy (EVAL-4): does the answer address the question, regardless of correctness?

This is distinct from faithfulness: an answer can be fully grounded yet evasive. The judge ignores
whether the answer is right and only scores whether it responds to what was asked.
"""

from __future__ import annotations

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.structured import complete_structured


class RelevancyVerdict(BaseModel):
    relevant: bool
    reason: str


def relevancy_score(
    client: LLMClient, question: str, answer: str, *, registry: ModelRegistry
) -> float:
    verdict = complete_structured(
        client,
        [{"role": "user", "content": f"Question: {question}\n\nAnswer:\n{answer}"}],
        RelevancyVerdict,
        model=registry.resolve("judge"),
        system=(
            "Decide whether the answer actually addresses the question, ignoring whether it is "
            'correct. Return JSON {"relevant": bool, "reason": str}. An evasive or off-topic '
            "answer is not relevant."
        ),
    )
    return 1.0 if verdict.relevant else 0.0
