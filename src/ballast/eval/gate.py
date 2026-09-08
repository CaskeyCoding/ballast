"""EVAL-13 local CI gate: thresholds -> exit code. Project 3's "block the merge", run locally.

GitHub Actions is not used here, so `make local-ci` calls this gate. It fails the build when the
hallucination rate exceeds its ceiling, refusal correctness drops below its floor, or p95 latency
regresses beyond the allowed fraction versus the previous committed run.

The gate also refuses to ride a stale green: if the newest ledger entry's sha is not HEAD or a
near ancestor of HEAD (within BALLAST_EVAL_GATE_MAX_BEHIND commits, default 3), it fails with a
"run make eval" message. For docs-only changes, set BALLAST_EVAL_GATE_ALLOW_STALE=1 to accept the
stale entry with a loud warning instead.
"""

from __future__ import annotations

import os
import subprocess

from ballast.core.config import load_thresholds
from ballast.eval.ledger import REPO_ROOT, read_history
from ballast.eval.regression import detect_regressions

STALE_OVERRIDE_ENV = "BALLAST_EVAL_GATE_ALLOW_STALE"
MAX_BEHIND_ENV = "BALLAST_EVAL_GATE_MAX_BEHIND"
DEFAULT_MAX_BEHIND = 3

# Metrics whose previous-run comparison is only meaningful over the same golden-set workload.
WORKLOAD_BOUND_METRICS = ("p95_latency_s", "mean_cost_usd")


def baseline_for_comparison(
    latest_entry: dict[str, object], previous_entry: dict[str, object]
) -> tuple[dict[str, float] | None, str | None]:
    """The previous entry's metrics to regress against, plus a note when part is dropped.

    Quality rates always compare. Latency and cost bands track the baseline run, so they are
    only comparable when both entries covered the same golden-set workload (equal recorded case
    counts, EVAL-23). When the set has grown (or the older entry predates `n` recording), the
    latency/cost baseline is dropped for this one transition; committing the new entry restores
    the band for every later run.
    """
    metrics = previous_entry.get("metrics")
    if not isinstance(metrics, dict):
        return None, None
    n_latest, n_prev = latest_entry.get("n"), previous_entry.get("n")
    if n_latest is not None and n_latest == n_prev:
        return metrics, None
    note = (
        f"latency/cost baseline skipped: golden-set workload changed or unrecorded "
        f"(previous n={n_prev}, latest n={n_latest}); quality metrics still compared"
    )
    return {k: v for k, v in metrics.items() if k not in WORKLOAD_BOUND_METRICS}, note


def check_gate(
    metrics: dict[str, float],
    thresholds: dict[str, float],
    *,
    previous: dict[str, float] | None = None,
) -> list[str]:
    failures: list[str] = []

    hr = metrics["hallucination_rate"]
    if hr > thresholds["hallucination_rate_max"]:
        failures.append(
            f"hallucination rate {hr:.1%} exceeds max {thresholds['hallucination_rate_max']:.1%}"
        )

    ra = metrics["refusal_accuracy"]
    if ra < thresholds["refusal_correctness_min"]:
        failures.append(
            f"refusal accuracy {ra:.1%} below min {thresholds['refusal_correctness_min']:.1%}"
        )

    ibr = metrics.get("injection_block_rate")  # absent in older ledger entries
    if ibr is not None:
        floor = thresholds.get("injection_block_rate_min", 0.0)
        if ibr < floor:
            failures.append(f"injection block rate {ibr:.1%} below min {floor:.1%}")

    if previous and previous.get("p95_latency_s", 0.0) > 0.0:
        allowed = previous["p95_latency_s"] * (1 + thresholds["latency_p95_regress_frac"])
        if metrics["p95_latency_s"] > allowed:
            failures.append(
                f"p95 latency {metrics['p95_latency_s']:.2f}s regressed beyond {allowed:.2f}s"
            )

    return failures


def commits_behind(entry_sha: str) -> int | None:
    """How many commits HEAD is ahead of the ledger entry, or None if undeterminable.

    Returns 0 when the entry sha is HEAD itself, a positive count when it is an ancestor of
    HEAD, and None when the sha is unknown to git, not an ancestor, or git is unavailable.
    """
    if not entry_sha or entry_sha == "unknown":
        return None
    try:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", entry_sha, "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        if ancestor.returncode != 0:
            return None
        out = subprocess.run(
            ["git", "rev-list", "--count", f"{entry_sha}..HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return int(out.stdout.strip())
    except Exception:
        return None


def staleness_failure(entry_sha: str, *, behind: int | None, max_behind: int) -> str | None:
    """A human-readable staleness reason, or None when the entry is fresh enough."""
    if behind is not None and behind <= max_behind:
        return None
    if behind is None:
        return f"newest eval ledger entry (sha {entry_sha}) is not HEAD or an ancestor of HEAD"
    return (
        f"newest eval ledger entry (sha {entry_sha}) is {behind} commits behind HEAD "
        f"(allowed: {max_behind})"
    )


def _check_staleness(entry_sha: str) -> int:
    """Print staleness diagnostics; nonzero means the gate must fail."""
    max_behind = int(os.environ.get(MAX_BEHIND_ENV, str(DEFAULT_MAX_BEHIND)))
    reason = staleness_failure(entry_sha, behind=commits_behind(entry_sha), max_behind=max_behind)
    if reason is None:
        return 0
    banner = "!" * 72
    print(banner)
    print("EVAL GATE STALENESS WARNING:")
    print(f"  {reason}.")
    print("  A green metric from that entry says nothing about the current code.")
    if os.environ.get(STALE_OVERRIDE_ENV) == "1":
        print(f"  {STALE_OVERRIDE_ENV}=1 is set: accepting the stale entry (docs-only override).")
        print(banner)
        return 0
    print("  Fix: run `make eval` (or `python -m ballast.eval.run_cli`) and commit the ledger,")
    print(f"  or set {STALE_OVERRIDE_ENV}=1 for a docs-only change.")
    print(banner)
    return 1


def main() -> int:
    history = read_history()
    if not history:
        print("eval gate: no history yet, skipping")
        return 0
    stale = _check_staleness(str(history[-1].get("sha", "unknown")))
    latest = history[-1]["metrics"]
    assert isinstance(latest, dict)
    prev: dict[str, float] | None = None
    if len(history) >= 2:
        prev, note = baseline_for_comparison(history[-1], history[-2])
        if note:
            print(f"eval gate: {note}")
    failures = check_gate(latest, load_thresholds(), previous=prev)
    if prev is not None:
        intervals = history[-1].get("intervals")
        failures += detect_regressions(
            latest, prev, intervals=intervals if isinstance(intervals, dict) else None
        )
    if failures:
        print("EVAL GATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    if stale:
        print("EVAL GATE FAILED: metrics pass but the ledger entry is stale (run `make eval`)")
        return 1
    print("eval gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
