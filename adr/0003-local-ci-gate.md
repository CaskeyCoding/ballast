# ADR 0003: A local CI gate instead of GitHub Actions

## Status

Accepted

## Context

Project 3 is an eval CI/CD harness: changes to the RAG or the gateway must be gated on quality
metrics, not only on unit tests. The obvious home for that gate is GitHub Actions. But Actions is
billing-disabled on this account, and the standing fleet convention is "test and deploy locally."
The repo also has no git remote; it merges to local `master`. A gate that depends on Actions minutes
would never run here.

## Options

- **GitHub Actions**: the conventional choice, but unavailable on this account and pointless for a
  remote-less repo. It would be aspirational config that never executes.
- **No gate, rely on discipline**: cheapest, but the whole point of Project 3 is an enforced gate;
  dropping it guts the project.
- **A local pre-PR gate that mirrors the `/local-ci` pattern**: a single script runs the same steps
  Actions would (secret scan, dep audit, ruff, mypy, pytest, and the eval gate), returns non-zero on
  any regression, and can be wired to a git pre-push hook.

## Decision

The gate is `scripts/local_ci.py`, run via `make local-ci` (and directly on this box, which has no
`make`). `eval/gate.py` returns a non-zero exit when the hallucination rate exceeds its threshold or
latency regresses, a committed metrics ledger plus a local static dashboard show the trend, and the
loop never commits on a red gate.

## Consequences

The CI/CD concept is fully preserved: the same checks, the same fail-the-build semantics, just not
dependent on Actions. Enforcement is by convention (the loop runs the gate before every commit)
rather than a server-side branch protection rule, so it relies on the loop honoring it. Porting to
Actions later is a thin YAML wrapper that shells out to the same script, so nothing is thrown away.
