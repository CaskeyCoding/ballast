# ballast — Design

Status: ready
Date: 2026-06-26
Owner: Eric

## One-line

A single Python monorepo that demonstrates three composing LLM-engineering patterns over one
shared core: a self-healing RAG pipeline, a guardrails gateway that wraps it, and an eval CI/CD
gate that tests it. Portfolio and learning grade.

## Why these three together

The three projects from the source screenshots are not independent. They form one system:

- The **RAG pipeline** is the core product (retrieve, generate, critique, retry).
- The **Guardrails gateway** is middleware that wraps the RAG (input, output, and policy checks).
- The **Eval CI/CD** harness is the test suite that gates changes to the RAG and the gateway.

Building them as one monorepo over a shared `core/` (LLM client, vector store, corpus) turns the
natural composition into real code instead of three disconnected demos, and removes the triplicate
scaffolding that three separate repos would create. Each subsystem is still an independent epic and
loops independently.

## The corpus is the "best application"

The RAG knowledge base is Eric's **public, non-sensitive** finance and investing methodology
(published public methodology and blog content). This is deliberate:

- It is a real, on-brand corpus instead of synthetic filler.
- The guardrails policy maps exactly to a real compliance need: "never give personalized financial
  advice," "always cite sources," "no medical or legal advice." That policy file is reusable beyond
  this repo.
- The eval golden set is genuine investing Q&A.

It stays clear of personal data entirely. No personal financial data of any kind ever enters this
repo.

## Scope boundary

In scope: a working, locally runnable end-to-end system with a CLI and a local dashboard.

Out of scope for the weekend: cloud deploy, auth, a hosted UI, multi-tenant isolation, and any wiring
into other systems. Those are explicit non-goals and must not appear in the backlog.

## Architecture

```
ballast/
  core/         shared foundation
    llm.py        LLMClient protocol + ClaudeClient (anthropic SDK), model registry, retry, cost meter
    store.py      VectorStore protocol + ChromaStore (persist, similarity search)
    ingest.py     corpus loader: markdown -> chunks -> embeddings -> store, with source metadata
    trace.py      structured run trace + token/cost/latency counters
    config.py     env + thresholds loading
  rag/          Project 1: self-healing RAG (LangGraph stateful graph)
    state.py      RAGState TypedDict (question, docs, answer, critique, retries, ...)
    nodes.py      retrieve, grade_documents, generate, critic, rewrite_query, fallback
    graph.py      StateGraph wiring with conditional edges + retry loop
    ask.py        CLI entrypoint that runs the graph and streams the trace
  gateway/      Project 2: guardrails middleware (wraps rag)
    gateway.py    request/response envelope, pre/post hook pipeline
    input/        pii.py, injection.py
    output/       schema.py, toxicity.py
    policy.py     declarative YAML policy engine (the non-engineer-editable layer)
    policy.yaml   the rules
  eval/         Project 3: eval CI/CD
    golden.jsonl  100+ QA pairs incl. edge cases
    metrics/      faithfulness.py, relevancy.py, hallucination.py, perf.py
    runner.py     run pipeline over golden set -> metrics JSON
    gate.py       thresholds -> exit code (local CI gate)
    history.jsonl committed metrics ledger keyed by git SHA
    dashboard/    static HTML trend view
  obs/          observability: per-run trace store, single-run viewer, cost/usage view
  corpus/       ingested public methodology + blog markdown (source documents)
  examples/     walkthrough + demo scripts
  adr/          architecture decision records
  runs/         per-run trace dumps (gitignored)
  specs/        DESIGN.md (this) + BACKLOG.md
  Makefile      local-ci, ingest, ask, eval, dashboard, demo, help targets
  pyproject.toml
```

## Data flow (happy path and self-heal)

1. User question enters the **gateway**. Input guardrails run (PII, injection). If blocked, return a
   safe fallback and stop.
2. The gateway calls the **RAG graph**. The graph: retrieve chunks, grade them for relevance,
   generate an answer, then a **critic** node checks groundedness.
3. If the critic fails the answer, a conditional edge routes to **rewrite_query** and loops back to
   retrieve. A retry counter in state caps the loop. When the cap is hit, the graph returns a
   graceful "I do not have enough information" instead of guessing.
4. The answer (with citations) returns to the **gateway**. Output guardrails run (schema, toxicity,
   policy). On failure the gateway either auto-retries with a corrected prompt or returns the safe
   fallback.
5. Every run writes a **trace** (nodes visited, tokens, cost, latency, decisions) for eval and debugging.

## Stack

- Python 3.12.
- **LangGraph** for the cyclical RAG graph. Self-healing is a conditional edge plus a retry counter
  in a `TypedDict` state (current API: `StateGraph`, `add_node`, `add_conditional_edges`,
  `add_edge`, `START`/`END`, `Annotated[list, operator.add]` reducers).
- **Claude API** (anthropic SDK), Claude-first. `claude-haiku-4-5` for high-volume cheap calls
  (critic, graders, guardrail classifiers); `claude-sonnet-4-6` for generation. Behind a thin
  `LLMClient` protocol so the eval "swap a model" goal is real and not bolted on.
- **Chroma** local vector store with sentence-transformers embeddings (zero extra API keys, zero
  infra). Voyage embeddings noted as a future upgrade.
- **Pydantic** for output-schema guardrails. PII and injection detectors are hand-rolled for the
  learning value, with guardrails-ai and NeMo Guardrails noted as reference implementations only.

## The one hard constraint: CI runs locally

GitHub Actions is billing-disabled on this account (standing "test and deploy locally" mode). So
the Eval CI/CD gate is a **local** pre-PR gate that mirrors the `/local-ci` pattern: `eval/gate.py`
returns a non-zero exit code when the hallucination rate exceeds the threshold or latency regresses
beyond the SLA, an optional git pre-commit or pre-push hook runs it, and a committed metrics ledger
plus a local static dashboard show the trend over commits. The CI/CD concept is fully preserved; it
just does not depend on Actions minutes.

## Backlog and the loop

One `specs/BACKLOG.md` in the standard machine-readable item format. Eight epics: `core`, `corpus`, `rag`, `gateway`, `eval`,
`obs` (observability), `sec` (security and hardening), and `dx` (docs and demo). Each item carries
`why`, `tests`, and `files` guidance beyond the parsed fields, and dependencies sequence the work.

Prioritization is milestone-driven rather than epic-driven, so a partial drain still yields a working
system:

- **M1 Walking skeleton (P0):** ingest the corpus, ask a question, get a cited answer end to end.
- **M2 Self-healing (P1):** critic, relevance grading, re-retrieve loop, retry cap, graceful decline.
- **M3 Guardrailed (P1/P2):** the gateway wraps the RAG with input, output, and policy guardrails.
- **M4 Eval-gated (P2):** golden set, core metrics, the local CI gate, the trend ledger.
- **M5 Depth and hardening (P2/P3):** retrieval quality, observability, security, eval rigor, DX.

A single weekend realistically lands M1 and most of M2/M3; M4 and M5 are the depth tail, sequenced so
the loop keeps producing reviewable PRs after the demo works. The loop is open-PR-only by default: one
item per run on a branch, then a PR; the human reviews and merges. To run it against this repo, point
the backlog tooling at this directory (the format matches `backlog.py`).

## Testing

Each `core` and `gateway` unit is testable in isolation through its protocol (fake LLM client, fake
store). The RAG graph is tested with a stubbed retriever and a scripted critic so the self-heal loop
and the retry cap are deterministic. The eval harness is itself the integration test for the whole
pipeline. Target: every backlog item ships with tests, and `make local-ci` is green before any PR.

## Non-goals (do not let the backlog drift into these)

- No cloud deploy, no hosted UI, no auth, no multi-tenant.
- No use of personal financial data of any kind. Public methodology only.
- No wiring into, or changes to, any separate private system or its specs.
- No new LLM provider beyond the Claude default until the eval seam demonstrably needs it.
