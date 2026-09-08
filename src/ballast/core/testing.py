"""FakeLLMClient: a deterministic `LLMClient` stand-in so the platform is testable with no key.

Two modes, combinable:
  - scripted: return a fixed list of responses by call order (raises when exhausted),
  - rules: return the first response whose predicate matches the messages (with a fallback default).

Token counts are estimated (len // 4) so cost and perf metrics have something to aggregate in tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence

from ballast.core.llm import LLMResponse, Message

Predicate = Callable[[Sequence[Message]], bool]


class FakeLLMClient:
    """A scripted/rule-based `LLMClient` for deterministic tests."""

    def __init__(
        self,
        scripted: Sequence[str] | None = None,
        *,
        rules: Sequence[tuple[Predicate, str]] | None = None,
        default: str | None = None,
        model_name: str = "fake-model",
    ) -> None:
        self._scripted = list(scripted or [])
        self._rules = list(rules or [])
        self._default = default
        self._model_name = model_name
        self.calls: list[dict[str, object]] = []  # recorded for assertions

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append({"messages": list(messages), "model": model, "system": system})
        text = self._next_text(messages)
        prompt_chars = sum(len(m.get("content", "")) for m in messages) + len(system or "")
        return LLMResponse(
            text=text,
            model=model or self._model_name,
            input_tokens=max(1, prompt_chars // 4),
            output_tokens=max(1, len(text) // 4),
            stop_reason="end_turn",
        )

    def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Yield the next response in word-sized chunks, mimicking token streaming."""
        self.calls.append({"messages": list(messages), "model": model, "system": system})
        text = self._next_text(messages)
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else word + " "

    def _next_text(self, messages: Sequence[Message]) -> str:
        if self._scripted:
            return self._scripted.pop(0)
        for predicate, response in self._rules:
            if predicate(messages):
                return response
        if self._default is not None:
            return self._default
        raise AssertionError(
            "FakeLLMClient exhausted: no scripted response, no matching rule, no default"
        )
