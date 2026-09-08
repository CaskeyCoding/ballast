"""PII input guardrail: detect Luhn-checked cards, SSNs, emails, and phone numbers.

Cards are Luhn-validated to cut false positives (a random 16-digit string is not a card). Phone and
SSN use digit-boundary lookarounds so they do not fire inside a longer run. Mode: block or redact.
"""

from __future__ import annotations

import re

from ballast.gateway.types import HookResult, Request

_CARD_RUN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PIIGuard:
    name = "pii"

    def __init__(self, mode: str = "block") -> None:
        self.mode = mode  # "block" or "redact"

    def check(self, request: Request) -> HookResult:
        text = request.question
        found: list[str] = []
        redacted = text

        for m in _CARD_RUN.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and _luhn(digits):
                found.append("card")
                redacted = redacted.replace(m.group(), "[REDACTED_CARD]")

        for label, rx, token in (
            ("ssn", _SSN, "[REDACTED_SSN]"),
            ("email", _EMAIL, "[REDACTED_EMAIL]"),
            ("phone", _PHONE, "[REDACTED_PHONE]"),
        ):
            if rx.search(redacted):
                found.append(label)
                redacted = rx.sub(token, redacted)

        if not found:
            return HookResult.allow()
        kinds = ", ".join(dict.fromkeys(found))
        if self.mode == "redact":
            return HookResult.modify_request(
                Request(redacted, request.metadata), "pii", f"redacted {kinds}"
            )
        return HookResult.block("pii", f"input contains {kinds}")
