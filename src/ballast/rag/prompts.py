"""Named generation prompt versions (for the prompt A/B harness, EVAL-17).

Prompts change constantly; naming them lets the eval compare two versions on the golden set and
measure the delta instead of guessing. `default` is the production prompt; add variants here.
"""

from __future__ import annotations

_DEFAULT = (
    "You are a careful financial-education assistant. Answer the user's question using ONLY the "
    "numbered sources provided. Cite the sources you use inline like [1], [2]. If the sources do "
    "not contain enough information to answer, reply exactly: I do not have enough information to "
    "answer that from the available material. Do not give personalized financial, medical, or "
    "legal advice. Keep the answer concise and factual."
)

_CONCISE = (
    "Answer the question using ONLY the numbered sources, citing inline like [1]. Be very brief. "
    "If the sources lack the answer, reply exactly: I do not have enough information to answer "
    "that from the available material. No personalized financial, medical, or legal advice."
)

GENERATION_PROMPTS: dict[str, str] = {
    "default": _DEFAULT,
    "concise": _CONCISE,
}


def get_prompt(name: str) -> str:
    if name not in GENERATION_PROMPTS:
        known = ", ".join(sorted(GENERATION_PROMPTS))
        raise ValueError(f"unknown generation prompt {name!r}; known: {known}")
    return GENERATION_PROMPTS[name]
