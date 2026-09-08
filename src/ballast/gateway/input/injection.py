"""Prompt-injection input guardrail: heuristic patterns for override and exfiltration attempts.

This is the cheap first line of defense before spending a model call (GW-5 escalates ambiguous
cases to a classifier). The pattern list lives here so adding a known technique needs no other edit.
"""

from __future__ import annotations

import re

from ballast.gateway.types import HookResult, Request

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore (all |the )?(previous|prior|above) (instructions|prompts?)", re.I),
    # "your rules"/"my instructions" variants: EVAL-23 (adv-3 evaded the previous/prior form)
    re.compile(
        r"disregard (all |the |your |my )?(previous|prior|above|rules?|instructions?)", re.I
    ),
    re.compile(r"(reveal|show|print|repeat) (me )?(your )?(system )?(prompt|instructions)", re.I),
    re.compile(r"you are now\b", re.I),
    re.compile(r"\bdeveloper mode\b", re.I),
    re.compile(r"pretend (to be|you are)\b", re.I),
    re.compile(r"\bDAN\b"),  # common jailbreak persona
]


class InjectionGuard:
    name = "injection"

    def check(self, request: Request) -> HookResult:
        for rx in _PATTERNS:
            if rx.search(request.question):
                return HookResult.block("injection", "input matches a prompt-injection pattern")
        return HookResult.allow()
