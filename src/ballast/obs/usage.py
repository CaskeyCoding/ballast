"""Cost and usage view across runs (OBS-3): aggregate tokens and cost from saved traces.

Makes the running cost of the system visible and attributable. `make usage` sums spend and
tokens by model across recent run traces, and shows how often each node executed. (Calls are
not node-tagged, so cost is attributed by model; the node view shows activity counts.)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ballast.obs.store import RUNS_DIR


@dataclass
class Usage:
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)
    by_node: dict[str, int] = field(default_factory=dict)


def load_runs(runs_dir: Path = RUNS_DIR) -> list[dict[str, Any]]:
    if not runs_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def aggregate_usage(traces: list[dict[str, Any]]) -> Usage:
    usage = Usage()
    by_model: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost_usd": 0.0, "tokens": 0.0, "calls": 0.0}
    )
    by_node: Counter[str] = Counter()
    for trace in traces:
        for call in trace.get("calls", []):
            m = by_model[call["model"]]
            m["cost_usd"] += float(call.get("cost_usd", 0.0))
            m["tokens"] += int(call.get("input_tokens", 0)) + int(call.get("output_tokens", 0))
            m["calls"] += 1
            usage.total_cost_usd += float(call.get("cost_usd", 0.0))
            usage.total_tokens += int(call.get("input_tokens", 0)) + int(
                call.get("output_tokens", 0)
            )
        for node in trace.get("nodes", []):
            by_node[node["name"]] += 1
    usage.by_model = dict(by_model)
    usage.by_node = dict(by_node)
    return usage


def main() -> None:
    usage = aggregate_usage(load_runs())
    print(f"runs aggregated from {RUNS_DIR}")
    print(f"total: ${usage.total_cost_usd:.5f}  {usage.total_tokens} tokens")
    print("by model:")
    for model, m in sorted(usage.by_model.items()):
        print(f"  {model}: ${m['cost_usd']:.5f}  {int(m['tokens'])} tok  {int(m['calls'])} calls")
    print("by node (executions):")
    for node, count in sorted(usage.by_node.items()):
        print(f"  {node}: {count}")


if __name__ == "__main__":
    main()
