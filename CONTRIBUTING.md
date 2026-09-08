# Contributing

This repo is built by a backlog-driven internal loop. Work is queued in `specs/BACKLOG.md`, picked
one item at a time, implemented behind a green gate, and committed to local `master`; the loop
merges locally instead of opening a PR. A public snapshot is published to GitHub from a dedicated
branch (see `PUBLISHING.md`), and external pull requests are not currently accepted. This guide is
how to run that workflow yourself or hand it to the next session.

## Setup

```
python -m pip install -e ".[dev]"   # or: make install
```

The governing design is `specs/DESIGN.md` (stack and non-goals; do not relitigate them per-item).
The decision records are in `adr/index.md`.

## The local loop

Each iteration does exactly one backlog item:

1. **Pick** the next ready item:
   `python specs/_shared/tooling/backlog.py next` (prints `NONE` when the queue is drained).
2. **Claim** it: `python specs/_shared/tooling/backlog.py start <ID>` (open -> in-progress).
3. **Implement** scoped strictly to the item's `accept`, following the existing patterns: protocols
   in `src/ballast/core/`, hooks in `src/ballast/gateway/`, nodes in
   `src/ballast/rag/`, metrics in `src/ballast/eval/`. All LLM calls go through
   `core.llm.LLMClient`, never the anthropic SDK directly outside `core`. Write tests with
   `FakeLLMClient` so they need no API key.
4. **Verify**: run `python scripts/local_ci.py` until it prints `local-ci PASSED`. Never commit a red
   gate.
5. **Commit** to master: `git commit -am "<type>: <ID> <summary>"`.
6. **Close** it: `python specs/_shared/tooling/backlog.py close <ID>` (sets status: done).

The loop is driven by the `/loop /llm-backlog` command, which re-invokes one iteration at a time.

## The gate

`python scripts/local_ci.py` is the merge gate. It runs, in order: a secret scan
(`scripts/secret_scan.py`), a leak scan (`scripts/leak_scan.py`), a dependency audit
(`scripts/dep_audit.py`), `ruff check`, `ruff format --check`, `mypy`, `pytest`, and the eval gate
(`python -m ballast.eval.gate`). The eval gate also fails when the newest `eval/history.jsonl`
entry is stale relative to HEAD (more than a few commits behind); refresh it with `make eval`, or
set `BALLAST_EVAL_GATE_ALLOW_STALE=1` for a docs-only change. The line-length limit is 100. Fix
lint with `python -m ruff format src tests` and `python -m ruff check --fix src tests`. The same
surface is available through the Makefile; run `make help` to list every target.

## Definition of done (every item)

1. Code plus unit tests; `python scripts/local_ci.py` prints `local-ci PASSED`.
2. No em dashes in code, comments, docs, or output (project style rule).
3. No private finance data anywhere; public methodology corpus only (see `specs/DESIGN.md` non-goals
   and `adr/0005-public-methodology-corpus.md`).
4. All LLM calls go through `core.llm.LLMClient`; never the anthropic SDK directly outside `core`.
5. No external API failure collapses to a silent zero; use a tri-state result (ok / stale / failed).
6. The commit message names the item id and a one-line summary.

## Guardrails

- One item per loop iteration. Do not chain into the next.
- This loop may commit locally but must never `git push` and never deploy. Publishing the public
  snapshot is a separate, deliberate step (`PUBLISHING.md`), guarded by a local pre-push hook.
- If an item's `accept` cannot be met without a product decision, do the smallest honest thing (often
  an investigate or propose note), run `python specs/_shared/tooling/backlog.py block <ID> "<why>"`,
  and stop rather than guessing.
