"""Content-addressed LLM response cache for repeatable, cheaper evals.

`CachingClient` wraps any `LLMClient`: identical requests (same model, messages, system, sampling
params) return a stored response instead of re-billing the API. Off by default in production paths;
the eval runner turns it on so an unchanged pipeline produces identical metrics across runs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ballast.core.llm import LLMResponse, Message


def _key(
    model: str, messages: Sequence[Message], system: str | None, max_tokens: int, temperature: float
) -> str:
    blob = json.dumps(
        {
            "model": model,
            "messages": list(messages),
            "system": system,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ResponseCache:
    """In-memory content-addressed store of completions (the raw provider object is not kept)."""

    enabled: bool = True
    _store: dict[str, LLMResponse] = field(default_factory=dict)

    def get(self, key: str) -> LLMResponse | None:
        return self._store.get(key) if self.enabled else None

    def put(self, key: str, resp: LLMResponse) -> None:
        if self.enabled:
            self._store[key] = resp

    def save(self, path: Path) -> None:
        """Persist the cache so a later run reuses identical responses (EVAL-20 determinism)."""
        data = {
            k: {
                "text": v.text,
                "model": v.model,
                "input_tokens": v.input_tokens,
                "output_tokens": v.output_tokens,
                "stop_reason": v.stop_reason,
            }
            for k, v in self._store.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, *, enabled: bool = True) -> ResponseCache:
        cache = cls(enabled=enabled)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            cache._store = {k: LLMResponse(**v) for k, v in data.items()}
        return cache


class CachingClient:
    """An `LLMClient` decorator that serves identical requests from a `ResponseCache`."""

    def __init__(self, base: object, cache: ResponseCache) -> None:
        self._base = base
        self._cache = cache
        self.misses = 0
        self.hits = 0

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        key = _key(model, messages, system, max_tokens, temperature)
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        resp: LLMResponse = self._base.complete(  # type: ignore[attr-defined]
            messages, model=model, system=system, max_tokens=max_tokens, temperature=temperature
        )
        self._cache.put(key, resp)
        return resp
