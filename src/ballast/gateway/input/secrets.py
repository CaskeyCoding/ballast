"""Secret/credential input guardrail: flag pasted API keys, tokens, and private keys."""

from __future__ import annotations

import re

from ballast.gateway.types import HookResult, Request

_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic/openai key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


class SecretGuard:
    name = "secrets"

    def __init__(self, mode: str = "block") -> None:
        self.mode = mode

    def check(self, request: Request) -> HookResult:
        hits = [label for label, rx in _PATTERNS.items() if rx.search(request.question)]
        if not hits:
            return HookResult.allow()
        kinds = ", ".join(hits)
        if self.mode == "redact":
            redacted = request.question
            for rx in _PATTERNS.values():
                redacted = rx.sub("[REDACTED_SECRET]", redacted)
            return HookResult.modify_request(
                Request(redacted, request.metadata), "secrets", f"redacted {kinds}"
            )
        return HookResult.block("secrets", f"input contains a credential ({kinds})")
