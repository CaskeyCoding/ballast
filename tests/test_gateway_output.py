"""GW-6/9/10/11: output schema guard and the YAML policy engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from ballast.gateway.fallback import INSUFFICIENT
from ballast.gateway.output.schema import SchemaGuard
from ballast.gateway.policy import PolicyGuard, load_rules
from ballast.gateway.types import Answer, Request

_REQ = Request("q")
_CIT = {"title": "T", "source": "S", "url": "U", "chunk_id": "c#0"}


# --- GW-6 schema ---
def test_schema_blocks_empty_answer() -> None:
    assert SchemaGuard().check(_REQ, Answer("   ", [])).action == "block"


def test_schema_blocks_malformed_citation() -> None:
    res = SchemaGuard().check(_REQ, Answer("ok", [{"title": "only"}]))
    assert res.action == "block" and "citation" in res.reason


def test_schema_allows_valid_answer() -> None:
    assert SchemaGuard().check(_REQ, Answer("a real answer", [_CIT])).action == "allow"


# --- GW-9/10 must-cite ---
def test_must_cite_blocks_uncited_substantive_answer() -> None:
    res = PolicyGuard.from_yaml().check(_REQ, Answer("Index funds track an index.", []))
    assert res.action == "block" and res.rule == "policy:always-cite-sources"


def test_must_cite_allows_cited_answer_and_refusal() -> None:
    guard = PolicyGuard.from_yaml()
    assert guard.check(_REQ, Answer("Index funds track an index.", [_CIT])).action == "allow"
    assert guard.check(_REQ, Answer(INSUFFICIENT, [])).action == "allow"  # a decline need not cite


# --- GW-11 prohibited advice ---
def test_personalized_advice_blocked() -> None:
    res = PolicyGuard.from_yaml().check(
        _REQ, Answer("You should buy NVDA right now to get rich.", [_CIT])
    )
    assert res.action == "block" and "personalized" in res.reason


def test_general_education_allowed() -> None:
    res = PolicyGuard.from_yaml().check(
        _REQ, Answer("Diversification spreads risk across many investments.", [_CIT])
    )
    assert res.action == "allow"


# --- GW-9 engine: custom policy + bad policy ---
def test_custom_policy_loads_and_enforces(tmp_path: Path) -> None:
    p = tmp_path / "policy.yaml"
    p.write_text(
        "rules:\n  - name: no-competitors\n    type: forbid_patterns\n"
        "    message: no competitor talk\n    patterns: ['acme corp']\n",
        encoding="utf-8",
    )
    guard = PolicyGuard.from_yaml(p)
    assert guard.check(_REQ, Answer("ACME Corp is better", [_CIT])).action == "block"


def test_unknown_rule_type_fails_loudly(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("rules:\n  - name: x\n    type: nonsense\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown type"):
        load_rules(p)
