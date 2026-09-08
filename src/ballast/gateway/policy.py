"""The policy engine: declarative YAML rules enforced as a post-hook (the configurable layer).

This is the distinguishing feature of Project 2. Rules live in policy.yaml; adding or editing one
needs no code change. Supported rule types: require_citation (must-cite, GW-10) and forbid_patterns
(prohibited advice, GW-11). A violating answer is blocked to a safe fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.types import Answer, HookResult, Request

DEFAULT_POLICY = Path(__file__).resolve().parent / "policy.yaml"
_VALID_TYPES = {"require_citation", "forbid_patterns"}


@dataclass
class PolicyRule:
    name: str
    type: str
    message: str
    patterns: list[re.Pattern[str]] = field(default_factory=list)


def _is_refusal(text: str) -> bool:
    return text.strip() == INSUFFICIENT


def load_rules(path: Path | None = None) -> list[PolicyRule]:
    path = path or DEFAULT_POLICY
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = []
    for raw in data.get("rules", []):
        rule_type = raw.get("type")
        if rule_type not in _VALID_TYPES:
            raise ValueError(f"policy rule {raw.get('name')!r} has unknown type {rule_type!r}")
        rules.append(
            PolicyRule(
                name=raw["name"],
                type=rule_type,
                message=raw.get("message", raw["name"]),
                patterns=[re.compile(p, re.I) for p in raw.get("patterns", [])],
            )
        )
    return rules


class PolicyGuard:
    name = "policy"

    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = rules

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> PolicyGuard:
        return cls(load_rules(path))

    def check(self, request: Request, answer: Answer) -> HookResult:
        for rule in self._rules:
            if rule.type == "require_citation":
                if not _is_refusal(answer.text) and not answer.citations:
                    return HookResult.block(f"policy:{rule.name}", rule.message)
            elif rule.type == "forbid_patterns":
                if any(p.search(answer.text) for p in rule.patterns):
                    return HookResult.block(f"policy:{rule.name}", rule.message)
        return HookResult.allow()
