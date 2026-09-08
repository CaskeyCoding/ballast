"""Typed safe-fallback answers the gateway returns instead of an unsafe or blocked response.

Centralizing them keeps the fallbacks explicit and testable rather than ad-hoc strings scattered
across hooks.
"""

from __future__ import annotations

from ballast.gateway.types import Answer

INSUFFICIENT = "I do not have enough information to answer that from the available material."


def blocked_input(reason: str) -> Answer:
    return Answer(text=f"Your message could not be processed: {reason}", citations=[])


def blocked_output(reason: str) -> Answer:
    return Answer(text=f"The response was withheld by a safety guardrail: {reason}", citations=[])


def insufficient() -> Answer:
    return Answer(text=INSUFFICIENT, citations=[])
