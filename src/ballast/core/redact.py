"""Redaction for logs and traces: mask cards, SSNs, emails, phones, and credentials in free text.

Catching PII at the gateway is pointless if the trace then writes it to disk in the clear (SEC-5).
This lives in `core` with its own small pattern set so nothing here depends upward on the gateway.
Cards are Luhn-checked so a random digit run is not masked as a card.
"""

from __future__ import annotations

import re

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
_SECRETS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


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


def redact(text: str) -> str:
    """Return `text` with cards, SSNs, emails, phones, and credentials masked."""
    if not text:
        return text

    def _card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group())
        return "[REDACTED_CARD]" if 13 <= len(digits) <= 19 and _luhn(digits) else m.group()

    out = _CARD.sub(_card, text)
    for rx in _SECRETS:
        out = rx.sub("[REDACTED_SECRET]", out)
    out = _SSN.sub("[REDACTED_SSN]", out)
    out = _EMAIL.sub("[REDACTED_EMAIL]", out)
    out = _PHONE.sub("[REDACTED_PHONE]", out)
    return out
