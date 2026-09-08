"""The swappable LLM seam: an `LLMClient` protocol and a Claude implementation.

Everything in the platform talks to this protocol, never the anthropic SDK directly. That is what
makes the eval "swap a model" goal real and lets every other module be unit-tested against the
FakeLLMClient (core/testing.py) with no API key.

`complete()` takes a logical role-resolved model id from the caller; retries are hand-rolled with
exponential backoff over the transient anthropic error classes so we add no extra dependency.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# A chat message. Kept deliberately minimal (role + text); tool use is out of scope for the seam.
Message = dict[str, str]


@dataclass(frozen=True)
class LLMResponse:
    """The normalized result of one completion, independent of provider."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None
    raw: Any = field(default=None, repr=False, compare=False)


class LLMError(RuntimeError):
    """Raised when a completion fails terminally (after exhausting retries)."""


@runtime_checkable
class LLMClient(Protocol):
    """The one interface the rest of the platform depends on."""

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


@runtime_checkable
class StreamingClient(Protocol):
    """Optional capability: yield text deltas as they arrive (RAG-9 token streaming)."""

    def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[str]: ...


# The anthropic exception classes we treat as transient and worth retrying.
_TRANSIENT_ERROR_NAMES = frozenset(
    {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}
)


def _is_transient(exc: BaseException) -> bool:
    names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(names & _TRANSIENT_ERROR_NAMES)


class ClaudeClient:
    """`LLMClient` backed by the Anthropic Messages API.

    The underlying SDK client is injectable (`client_factory`) so tests exercise retry and parsing
    without a network or a key. The SDK is imported lazily so importing this module costs nothing.
    """

    def __init__(
        self,
        api_key: str,
        *,
        client_factory: Callable[[str], Any] | None = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._sleep = sleep
        if client_factory is None:

            def client_factory(key: str) -> Any:
                from anthropic import Anthropic  # lazy: no import cost, no SDK needed for tests

                return Anthropic(api_key=key)

        self._client = client_factory(api_key)

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": list(messages),
        }
        if system is not None:
            kwargs["system"] = system

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                raw = self._client.messages.create(**kwargs)
                return _parse_response(raw, model)
            except Exception as exc:  # noqa: BLE001 - classified just below
                last_exc = exc
                if not _is_transient(exc) or attempt == self._max_retries:
                    raise LLMError(f"completion failed for model {model!r}: {exc}") from exc
                self._sleep(self._base_delay * (2**attempt))
        # unreachable: the loop either returns or raises, but keeps mypy total
        raise LLMError(f"completion failed for model {model!r}: {last_exc}")

    def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": list(messages),
        }
        if system is not None:
            kwargs["system"] = system
        try:
            with self._client.messages.stream(**kwargs) as stream:
                yield from stream.text_stream
        except Exception as exc:  # noqa: BLE001 - normalize to our typed error
            raise LLMError(f"streaming failed for model {model!r}: {exc}") from exc


def _parse_response(raw: Any, model: str) -> LLMResponse:
    """Normalize an anthropic Messages response into an LLMResponse."""
    text = "".join(getattr(block, "text", "") for block in getattr(raw, "content", []) or [])
    usage = getattr(raw, "usage", None)
    return LLMResponse(
        text=text,
        model=getattr(raw, "model", model),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        stop_reason=getattr(raw, "stop_reason", None),
        raw=raw,
    )
