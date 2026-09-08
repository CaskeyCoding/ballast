"""Run trace: the shared record of what happened in one ask or eval, serializable to JSON.

A `Trace` collects the sequence of node events and LLM calls (with tokens, cost, latency) plus
arbitrary decision records (a guardrail block, a critic verdict). The CLI prints it, observability
stores it, and the eval perf metrics aggregate latency and cost from it.

`MeteredClient` wraps any `LLMClient` to time each call, price it via the `CostMeter`, enforce the
budget, and append an `LLMCall` to the trace. It is what RAG and the gateway actually call, so cost
and tracing are automatic rather than something each node must remember to do.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from ballast.core.cost import CostMeter
from ballast.core.llm import LLMClient, LLMResponse, Message
from ballast.core.redact import redact


@dataclass
class LLMCall:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float


@dataclass
class NodeEvent:
    name: str
    detail: str = ""


@dataclass
class Decision:
    kind: str  # e.g. "critic", "guardrail", "fallback"
    outcome: str
    reason: str = ""


@dataclass
class Trace:
    run_id: str
    nodes: list[NodeEvent] = field(default_factory=list)
    calls: list[LLMCall] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def record_node(self, name: str, detail: str = "") -> None:
        self.nodes.append(NodeEvent(name=name, detail=detail))

    def record_call(self, call: LLMCall) -> None:
        self.calls.append(call)

    def record_decision(self, kind: str, outcome: str, reason: str = "") -> None:
        self.decisions.append(Decision(kind=kind, outcome=outcome, reason=reason))

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_latency_s(self) -> float:
        return sum(c.latency_s for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)

    def to_dict(self) -> dict[str, Any]:
        # Redact free-text fields so PII/secrets never land in a serialized trace (SEC-5).
        return {
            "run_id": self.run_id,
            "nodes": [{"name": n.name, "detail": redact(n.detail)} for n in self.nodes],
            "calls": [asdict(c) for c in self.calls],
            "decisions": [
                {"kind": d.kind, "outcome": d.outcome, "reason": redact(d.reason)}
                for d in self.decisions
            ],
            "totals": {
                "cost_usd": self.total_cost_usd,
                "latency_s": self.total_latency_s,
                "tokens": self.total_tokens,
            },
        }


class MeteredClient:
    """An `LLMClient` decorator that times, prices, budget-guards, and traces every call."""

    def __init__(
        self,
        base: LLMClient,
        meter: CostMeter,
        trace: Trace,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._base = base
        self._meter = meter
        self._trace = trace
        self._clock = clock

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self._meter.check()  # raises BudgetExceeded before overspending
        start = self._clock()
        resp = self._base.complete(
            messages,
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency = self._clock() - start
        cost = self._meter.add(resp.model, resp.input_tokens, resp.output_tokens)
        self._trace.record_call(
            LLMCall(
                model=resp.model,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=cost,
                latency_s=latency,
            )
        )
        return resp
