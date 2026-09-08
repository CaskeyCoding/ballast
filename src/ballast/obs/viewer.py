"""Single-run trace viewer (OBS-2): render one run's nodes, calls, and decisions readably.

A self-heal loop or a guardrail block is easier to understand from a laid-out view than from raw
JSON. `make trace RUN=<id>` loads runs/<id>.json and prints the node sequence, the LLM calls
(tokens, cost, latency), the decisions, and the totals.
"""

from __future__ import annotations

import argparse
from typing import Any

from ballast.obs.store import load_trace


def render_trace(trace: dict[str, Any]) -> str:
    lines = [f"run {trace['run_id']}", ""]

    lines.append("nodes:")
    for node in trace.get("nodes", []):
        detail = f" - {node['detail']}" if node.get("detail") else ""
        lines.append(f"  {node['name']}{detail}")

    decisions = trace.get("decisions", [])
    if decisions:
        lines.append("\ndecisions:")
        for d in decisions:
            reason = f": {d['reason']}" if d.get("reason") else ""
            lines.append(f"  [{d['kind']}] {d['outcome']}{reason}")

    calls = trace.get("calls", [])
    if calls:
        lines.append("\nllm calls:")
        for c in calls:
            lines.append(
                f"  {c['model']}  {c['input_tokens']}+{c['output_tokens']} tok  "
                f"${c['cost_usd']:.5f}  {c['latency_s']:.2f}s"
            )

    totals = trace.get("totals", {})
    lines.append(
        f"\ntotals: ${totals.get('cost_usd', 0):.5f}  "
        f"{totals.get('tokens', 0)} tok  {totals.get('latency_s', 0):.2f}s"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="View a saved run trace.")
    parser.add_argument("run_id", help="the run id (runs/<run_id>.json)")
    args = parser.parse_args()
    print(render_trace(load_trace(args.run_id)))


if __name__ == "__main__":
    main()
