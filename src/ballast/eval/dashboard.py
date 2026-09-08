"""EVAL-15 trend dashboard: a static HTML view of the metrics over commits.

Reads the committed ledger (history.jsonl) and renders inline-SVG line charts, so it opens as a
plain file with no server and no external CDN. Shows whether the system is improving or regressing.
"""

from __future__ import annotations

import html
from pathlib import Path

from ballast.eval.ledger import HISTORY_PATH, read_history

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = REPO_ROOT / "eval" / "dashboard" / "index.html"

# (metric key, label, "up" if higher-is-better else "down", colour)
_PANELS = [
    ("hallucination_rate", "Hallucination rate", "down", "#dc2626"),
    ("refusal_accuracy", "Refusal correctness", "up", "#16a34a"),
    ("faithfulness_mean", "Faithfulness", "up", "#2563eb"),
    ("p95_latency_s", "p95 latency (s)", "down", "#d97706"),
    ("mean_cost_usd", "Cost per query ($)", "down", "#7c3aed"),
]


def _svg_line(values: list[float], *, width: int = 480, height: int = 90, colour: str) -> str:
    if not values:
        return "<svg></svg>"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = (i / max(n - 1, 1)) * (width - 8) + 4
        y = height - 4 - ((v - lo) / span) * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    dots = "".join(
        f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="2.5" fill="{colour}"/>'
        for p in pts
    )
    return (
        f'<svg width="{width}" height="{height}" style="background:#f8fafc;border-radius:6px">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{colour}" stroke-width="2"/>'
        f"{dots}</svg>"
    )


def build_dashboard(history: list[dict[str, object]]) -> str:
    panels = []
    for key, label, direction, colour in _PANELS:
        series: list[float] = []
        for entry in history:
            metrics = entry.get("metrics", {})
            if isinstance(metrics, dict) and key in metrics:
                series.append(float(metrics[key]))
        latest = f"{series[-1]:.4f}" if series else "n/a"
        arrow = "lower is better" if direction == "down" else "higher is better"
        panels.append(
            f'<div class="panel"><div class="label">{html.escape(label)} '
            f'<span class="hint">({arrow})</span></div>'
            f'<div class="value">{latest}</div>{_svg_line(series, colour=colour)}</div>'
        )
    n = len(history)
    body = "\n".join(panels)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>ballast eval trend</title><style>"
        "body{font-family:system-ui,sans-serif;margin:2rem;background:#fff;color:#0f172a}"
        ".panel{margin:1.2rem 0;padding:1rem;border:1px solid #e2e8f0;border-radius:8px}"
        ".label{font-weight:600}.hint{color:#64748b;font-weight:400;font-size:.85em}"
        ".value{font-size:1.6rem;margin:.3rem 0}"
        "</style></head><body>"
        f"<h1>ballast eval trend</h1><p>{n} run(s) recorded.</p>{body}"
        "</body></html>"
    )


def main() -> None:
    history = read_history()
    if not history:
        print(f"no eval history at {HISTORY_PATH}; run `make eval` first")
        return
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(build_dashboard(history), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(history)} runs)")


if __name__ == "__main__":
    main()
