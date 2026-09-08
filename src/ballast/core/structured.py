"""Schema-enforced completions: ask the model for JSON, validate, and repair once on a miss.

Kept as a provider-agnostic free function over any `LLMClient` (including FakeLLMClient) rather than
a protocol method, so there is exactly one implementation of the validate-and-repair dance. The
critic, document graders, and guardrail classifiers all call this instead of parsing prose.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ballast.core.llm import LLMClient, LLMError, Message

T = TypeVar("T", bound=BaseModel)


class StructuredError(LLMError):
    """Raised when the model cannot produce schema-valid JSON even after a repair attempt."""


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a response that may wrap it in prose or a code fence."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop a leading ```json fence and the trailing ```
        body = stripped.split("```", 2)
        if len(body) >= 2:
            stripped = body[1]
            if stripped.startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def complete_structured(
    client: LLMClient,
    messages: Sequence[Message],
    schema: type[T],
    *,
    model: str,
    system: str | None = None,
    max_tokens: int = 1024,
) -> T:
    """Return an instance of `schema`, asking the model to repair once before raising."""
    schema_json = json.dumps(schema.model_json_schema())
    directive = (
        "Respond with ONLY a single JSON object that validates against this JSON Schema. "
        "No prose, no code fence.\n" + schema_json
    )
    full_system = f"{system}\n\n{directive}" if system else directive

    resp = client.complete(messages, model=model, system=full_system, max_tokens=max_tokens)
    try:
        return schema.model_validate_json(_extract_json(resp.text))
    except (ValidationError, json.JSONDecodeError) as first_err:
        repair: list[Message] = [
            *messages,
            {"role": "assistant", "content": resp.text},
            {
                "role": "user",
                "content": (
                    f"That did not validate: {first_err}. "
                    "Return ONLY the corrected JSON object, nothing else."
                ),
            },
        ]
        resp2 = client.complete(repair, model=model, system=full_system, max_tokens=max_tokens)
        try:
            return schema.model_validate_json(_extract_json(resp2.text))
        except (ValidationError, json.JSONDecodeError) as second_err:
            raise StructuredError(
                f"schema {schema.__name__} not satisfied after repair: {second_err}"
            ) from second_err
