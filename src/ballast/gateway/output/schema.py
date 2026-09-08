"""Output schema guardrail: the answer envelope must be well-formed before it leaves the gateway.

The RAG already produces structured output (LLM-JSON repair lives in core.structured for the critic
and graders); this post-hook is the final envelope check: non-empty text and citation entries that
carry the expected keys. A structurally invalid answer is blocked to a safe fallback.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError, field_validator

from ballast.gateway.types import Answer, HookResult, Request

_CITATION_KEYS = {"title", "source", "url", "chunk_id"}


class AnswerModel(BaseModel):
    text: str
    citations: list[dict[str, str]]

    @field_validator("text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("answer text is empty")
        return v


class SchemaGuard:
    name = "schema"

    def check(self, request: Request, answer: Answer) -> HookResult:
        try:
            AnswerModel(text=answer.text, citations=answer.citations)
        except ValidationError as exc:
            return HookResult.block(
                "schema", f"malformed answer envelope: {exc.error_count()} error"
            )
        for c in answer.citations:
            missing = _CITATION_KEYS - set(c)
            if missing:
                return HookResult.block("schema", f"citation missing keys: {sorted(missing)}")
        return HookResult.allow()
