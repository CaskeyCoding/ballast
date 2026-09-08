"""Faithfulness: an LLM judge decides whether an answer is supported by its cited sources.

Returns 1.0 (supported) or 0.0 (not). The hallucination rate (EVAL-6) is derived from this together
with the decline cases. The judge is a cheap model and goes through the same swappable client seam.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from ballast.core.config import ModelRegistry
from ballast.core.llm import LLMClient
from ballast.core.structured import complete_structured


class FaithfulnessVerdict(BaseModel):
    supported: bool
    reason: str


def faithfulness_score(
    client: LLMClient,
    question: str,
    answer: str,
    source_texts: Sequence[str],
    *,
    registry: ModelRegistry,
) -> float:
    sources = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(source_texts)) or "(no sources)"
    verdict = complete_structured(
        client,
        [
            {
                "role": "user",
                "content": f"Question: {question}\n\nSources:\n{sources}\n\nAnswer:\n{answer}",
            }
        ],
        FaithfulnessVerdict,
        model=registry.resolve("judge"),
        system=(
            "You judge whether EVERY claim in the answer is supported by the sources. Return JSON "
            '{"supported": bool, "reason": str}. supported is false if the answer states anything '
            "the sources do not back up."
        ),
    )
    return 1.0 if verdict.supported else 0.0
