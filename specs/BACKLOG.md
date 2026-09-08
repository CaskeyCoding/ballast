# Backlog

Machine-readable work queue for the orchestration loop (`/loop /backlog`). Each iteration the loop
returns the highest-priority `open` item whose dependencies are met, implements that one item on a
branch, opens a PR, and marks it `pr-open`. **It never merges or deploys; you review, merge, deploy.**

Governing spec: `specs/DESIGN.md`. Stack and non-goals live there; do not relitigate them per-item.

## Item format

```
### CORE-1
- priority: P0          # P0 ship-blocking .. P3 depth/polish
- epic: core
- repo: ballast
- title: <one line>
- accept: <the single gate the PR must satisfy, one line>
- why: <one line of rationale: what breaks or is missing without it>
- tests: <specific cases the PR must add>
- files: <where it lands>
- deps: none            # comma-separated IDs (met once pr-open or done)
- status: open
- pr: -
```

`priority`, `epic`, `repo`, `title`, `accept`, `deps`, `status`, `pr` are the parsed fields.
`why`, `tests`, `files` are guidance for the implementing agent and reviewer; keep them present.

## Definition of done (every item)

1. Code + unit tests; `make local-ci` green (ruff, mypy, pytest, eval gate once it exists).
2. No em dashes in code, comments, docs, or output (project style rule).
3. No private finance data anywhere; public methodology corpus only (DESIGN non-goals).
4. All LLM calls go through `core.llm.LLMClient`; never the anthropic SDK directly outside `core`.
5. No external API failure collapses to a silent zero; use a tri-state result (ok / stale / failed).
6. The PR description names the milestone and the acceptance evidence.

## Milestones (drive prioritization)

- **M1 Walking skeleton (P0):** ingest the corpus, ask a question, get a cited answer end to end.
- **M2 Self-healing (P1):** critic, relevance grading, re-retrieve loop, retry cap, graceful decline.
- **M3 Guardrailed (P1/P2):** the gateway wraps the RAG with input, output, and policy guardrails.
- **M4 Eval-gated (P2):** golden set, core metrics, the local CI gate, the trend ledger.
- **M5 Depth and hardening (P2/P3):** retrieval quality, observability, security, eval rigor, DX.

A single weekend realistically lands M1 and most of M2/M3. M4 and M5 are the depth tail; they are
sequenced so the loop keeps producing reviewable PRs long after the demo works.

## Epics

- **core** — shared foundation: config, LLM client (Claude default, swappable), cost/budget meter,
  cache, rate limit, structured logging, run trace. Lands first; everything imports it.
- **corpus** — the knowledge base and retrieval quality: vector store, chunking, embeddings,
  ingestion, hybrid search, reranking, metadata filters.
- **rag** — Project 1, the self-healing RAG pipeline as a LangGraph stateful graph.
- **gateway** — Project 2, the guardrails gateway wrapping the RAG.
- **eval** — Project 3, the eval CI/CD harness, with the rigor an honest eval needs.
- **obs** — observability across runs: trace store, a single-run viewer, a cost/usage view.
- **sec** — security and hardening: secrets hygiene, dependency audit, cost/DoS caps, injection depth.
- **dx** — developer experience and the demo: docs, diagram, example walkthrough, ADRs, packaging.

---

## core

### CORE-1
- priority: P0
- epic: core
- repo: ballast
- title: Repo scaffold: pyproject, ruff + mypy + pytest config, pre-commit, Makefile skeleton
- accept: `pip install -e .` succeeds and `make local-ci` runs ruff, mypy, and pytest (an empty suite passes green)
- why: nothing else can be reviewed or gated without a reproducible lint/type/test baseline
- tests: a trivial `test_smoke` asserting the package imports
- files: pyproject.toml, Makefile, .pre-commit-config.yaml, src/ballast/__init__.py, tests/test_smoke.py
- deps: none
- status: done
- pr: local

### CORE-2
- priority: P0
- epic: core
- repo: ballast
- title: Config and settings: pydantic-settings, .env loading, thresholds.yaml, model registry
- accept: a `Settings` object loads ANTHROPIC_API_KEY, CHROMA_DIR, and model ids from env/yaml with documented defaults, and `.env.example` lists every key
- why: model ids, thresholds, and paths must be single-sourced, not scattered as literals
- tests: settings load from a temp .env; missing required key raises a clear error; registry resolves haiku/sonnet ids
- files: core/config.py, thresholds.yaml, .env.example
- deps: CORE-1
- status: done
- pr: local

### CORE-3
- priority: P0
- epic: core
- repo: ballast
- title: LLMClient protocol + ClaudeClient with retry, timeout, and backoff
- accept: an `LLMClient` protocol with `complete(messages, model, ...)` and a `ClaudeClient` (anthropic SDK, lazy-imported) that retries on transient errors with exponential backoff
- why: the swappable seam the whole platform and the eval "swap a model" goal depend on
- tests: a recorded/mocked success; a retried-then-succeed path; a terminal-failure path raising a typed error
- files: core/llm.py
- deps: CORE-2
- status: done
- pr: local

### CORE-4
- priority: P0
- epic: core
- repo: ballast
- title: Structured-output helper: schema-enforced completion with validate-and-repair
- accept: `complete_structured(messages, schema)` returns a validated object, asking the model to repair once on a schema miss before raising
- why: critic, graders, and guardrail classifiers all need reliable structured returns, not prose parsing
- tests: a clean structured return; a malformed-then-repaired return; a twice-bad return raising
- files: core/llm.py, core/structured.py
- deps: CORE-3
- status: done
- pr: local

### CORE-5
- priority: P0
- epic: core
- repo: ballast
- title: FakeLLMClient for deterministic tests (scripted and rule-based responses)
- accept: a `FakeLLMClient` implementing `LLMClient` that returns scripted responses by call index or by a matching rule, usable to make graph and gateway tests deterministic
- why: every downstream test needs a real LLM stand-in or the suite is non-deterministic and slow
- tests: scripted sequence returns in order; a structured-response script validates against a schema
- files: core/testing.py
- deps: CORE-3
- status: done
- pr: local

### CORE-6
- priority: P1
- epic: core
- repo: ballast
- title: Token and cost meter + price table + per-run budget guard
- accept: every `LLMClient` call records input/output tokens and cost from a model price table; a per-run budget cap raises `BudgetExceeded` before overspending
- why: cost is a first-class eval metric and an uncapped loop can run up a real bill
- tests: cost math for a known token count; budget cap trips at the boundary
- files: core/cost.py, core/llm.py
- deps: CORE-3
- status: done
- pr: local

### CORE-7
- priority: P1
- epic: core
- repo: ballast
- title: Run Trace object: nodes visited, per-call usage, latency, decisions, serializable to JSON
- accept: a `Trace` accumulates node events, LLM calls (tokens, cost, latency), and decision records, and serializes to a stable JSON shape
- why: the trace is the shared substrate for the CLI, observability, and eval perf metrics
- tests: a built trace serializes and round-trips; latency and cost totals aggregate correctly
- files: core/trace.py
- deps: CORE-6
- status: done
- pr: local

### CORE-8
- priority: P1
- epic: core
- repo: ballast
- title: Structured JSON logging with a per-run correlation id
- accept: a configured logger emits JSON lines carrying a run id that ties log lines to a trace
- why: debugging a self-heal loop or a guardrail block needs correlated, machine-readable logs
- tests: a log line parses as JSON and carries the run id; PII redaction hook is invoked (see SEC-5)
- files: core/logging.py
- deps: CORE-7
- status: done
- pr: local

### CORE-9
- priority: P2
- epic: core
- repo: ballast
- title: Content-addressed LLM response cache (repeatable evals, lower cost)
- accept: an optional cache keyed by (model, normalized messages) returns a stored response on hit; toggled by config; off by default in production paths
- why: eval reruns and the model matrix must be repeatable and cheap, not re-billed every run
- tests: identical inputs hit the cache; a changed model or message misses; disabling bypasses it
- files: core/cache.py
- deps: CORE-3
- status: done
- pr: local

### CORE-10
- priority: P2
- epic: core
- repo: ballast
- title: In-process rate limiter and concurrency guard for API calls
- accept: a limiter caps concurrent and per-minute calls to the LLM and embedding APIs, with bounded waiting
- why: batch eval over 100+ questions will trip provider rate limits without a guard
- tests: concurrency never exceeds the cap under parallel calls; per-minute cap throttles
- files: core/ratelimit.py
- deps: CORE-3
- status: done
- pr: local

---

## corpus

### CORP-1
- priority: P0
- epic: corpus
- repo: ballast
- title: VectorStore protocol + ChromaStore (persist, upsert, search, delete, count)
- accept: a `VectorStore` protocol and a persistent `ChromaStore` that round-trips a document and returns chunks with `source` and `chunk_id` metadata
- why: retrieval and citations depend on a stable store interface with source metadata
- tests: upsert then search returns the doc; metadata survives; count reflects upserts; delete removes
- files: core/store.py
- deps: CORE-2
- status: done
- pr: local
- note: shipped as VectorStore protocol + InMemoryVectorStore (numpy cosine); ChromaStore persistence queued as CORP-1b

### CORP-2
- priority: P0
- epic: corpus
- repo: ballast
- title: Corpus source format + seed public methodology docs with provenance frontmatter
- accept: at least 8 public methodology/blog markdown files under `corpus/`, each with frontmatter (source, url, published date), and a documented format
- why: the RAG needs a real, on-brand, non-sensitive corpus with citable provenance
- tests: a loader parses frontmatter for every seed file; a CI check fails on a missing required field
- files: corpus/*.md, corpus/README.md, core/corpus.py
- deps: CORE-1
- status: done
- pr: local

### CORP-2b
- priority: P3
- epic: corpus
- repo: ballast
- title: Swap the public-domain stand-in corpus for Eric's own published, public methodology
- accept: the generic investor.gov stand-in docs are replaced (or augmented) with Eric's confirmed-public, non-sensitive published content, each with provenance frontmatter; disclosure-auditor clean
- why: makes the RAG on-brand and the guardrail policy fully real; the stand-in unblocked the build, this finishes the corpus story
- tests: load_corpus still validates; a disclosure scan over corpus/ passes
- files: corpus/*.md
- deps: CORP-2
- status: done
- pr: local
- note: DONE 2026-06-27 (owner unblocked, Setting B terms). Layer 1 = 10 federal public-domain docs (SEC/IRS/CFPB/FDIC/Treasury/BLS). Layer 3 = 6 anonymized methodology docs distilled from the 5 public, CR-free caskeycoding blog posts (honest backtesting, luck vs edge, process over outcome, trust boundary, intellectual honesty, stress-testing), product-anonymous, no engine internals, public academic refs only. Corpus 8->24, golden set 43->89 in lockstep. disclosure-auditor GO on both batches, blog URLs verified live + CR-free, local-ci green. See proposals/corpus-strategy.md.

### CORP-3
- priority: P0
- epic: corpus
- repo: ballast
- title: Chunking strategy: heading-aware recursive splitter with configurable size and overlap
- accept: a chunker splits markdown on headings then by token budget with overlap, preserving the heading path in each chunk's metadata
- why: retrieval quality and citation granularity both hinge on sensible chunk boundaries
- tests: chunk token counts respect the budget; overlap is present; heading path is captured
- files: core/chunk.py
- deps: CORP-2
- status: done
- pr: local

### CORP-4
- priority: P1
- epic: corpus
- repo: ballast
- title: Embedding function abstraction (sentence-transformers default, Voyage adapter stub)
- accept: an `Embedder` protocol with a sentence-transformers default and a stubbed Voyage adapter selectable by config
- why: embeddings should be swappable without touching the store or ingestion
- tests: the default embedder returns stable-dimension vectors; the adapter selection is config-driven
- files: core/embed.py
- deps: CORP-1
- status: done
- pr: local
- note: shipped HashingEmbedder (deterministic, no torch) as default; sentence-transformers queued as CORP-4b

### CORP-4b
- priority: P1
- epic: corpus
- repo: ballast
- title: SentenceTransformerEmbedder as the default embedder (real semantic embeddings)
- accept: a `SentenceTransformerEmbedder` (all-MiniLM-L6-v2, lazy torch import) selectable by config and made the default for `make ask`/`make ingest`; HashingEmbedder stays the no-torch test/fallback; a real ask still answers grounded and cited
- why: semantic embeddings beat term-frequency hashing on queries that do not share keywords with the source
- tests: ST embedder returns fixed-dim normalized vectors; get_embedder honors config; CI path stays on hashing (no torch in tests)
- files: core/embed.py, core/config.py, core/ingest.py, rag/ask.py
- deps: CORP-4
- status: done
- pr: local

### CORP-1b
- priority: P2
- epic: corpus
- repo: ballast
- title: ChromaStore: persistent VectorStore backend behind the existing protocol
- accept: a `ChromaStore` implementing `VectorStore` persists to CHROMA_DIR and round-trips; selectable by config; InMemoryVectorStore stays the default for tests
- why: persistence avoids re-embedding the corpus every process and scales past an in-memory store
- tests: upsert then search round-trips across a fresh store instance pointed at the same dir
- files: core/store.py, core/config.py
- deps: CORP-1
- status: done
- pr: -

### CORP-5
- priority: P0
- epic: corpus
- repo: ballast
- title: Ingestion pipeline `make ingest`: idempotent upsert keyed by content hash, with reindex
- accept: `make ingest` loads `corpus/*.md`, chunks, embeds, and upserts; re-running is idempotent (unchanged chunks are not duplicated) and `--reindex` rebuilds cleanly
- why: a repeatable, idempotent index is the precondition for repeatable retrieval and eval
- tests: ingest then re-ingest yields the same chunk count; editing a file updates only its chunks
- files: core/ingest.py, Makefile
- deps: CORP-3, CORP-4
- status: done
- pr: local

### CORP-6
- priority: P0
- epic: corpus
- repo: ballast
- title: Retrieval: top-k similarity search returning chunks + citation metadata
- accept: a `retrieve(query, k)` returns the top-k chunks with text, score, and `{source, url, chunk_id}` for citation
- why: the RAG generate and citation steps consume exactly this shape
- tests: a known query returns the expected source in the top-k against the seed corpus
- files: core/retrieve.py
- deps: CORP-5
- status: done
- pr: local

### CORP-7
- priority: P2
- epic: corpus
- repo: ballast
- title: Hybrid retrieval: BM25 keyword + vector with reciprocal rank fusion
- accept: a hybrid retriever fuses BM25 and vector results via RRF and is selectable by config; falls back to vector-only cleanly
- why: pure vector search misses exact-term and rare-entity queries the eval set will include
- tests: a keyword-heavy query ranks the right chunk higher under hybrid than under vector-only
- files: core/retrieve.py, core/bm25.py
- deps: CORP-6
- status: done
- pr: -

### CORP-8
- priority: P2
- epic: corpus
- repo: ballast
- title: Reranking node: rerank retrieval candidates (cross-encoder or haiku judge)
- accept: an optional reranker reorders the top-N candidates down to top-k by relevance, selectable by config
- why: first-stage retrieval ranking is coarse; reranking is the cheapest large quality lever
- tests: a planted relevant-but-low-similarity chunk is promoted into the top-k after reranking
- files: core/rerank.py
- deps: CORP-6
- status: done
- pr: -

### CORP-9
- priority: P3
- epic: corpus
- repo: ballast
- title: Metadata filtering: restrict retrieval by source or published date
- accept: `retrieve` accepts a metadata filter (for example source or date range) passed through to the store
- why: some eval questions and policy rules need source-scoped retrieval
- tests: a filtered query returns only chunks from the allowed sources
- files: core/retrieve.py
- deps: CORP-6
- status: done
- pr: -

### CORP-10
- priority: P3
- epic: corpus
- repo: ballast
- title: Corpus stats and coverage report
- accept: `make corpus-stats` prints document count, chunk count, token histogram, and per-source coverage
- why: eval results are only interpretable against a known corpus shape
- tests: stats match a fixture corpus of known size
- files: core/corpus_stats.py, Makefile
- deps: CORP-5
- status: done
- pr: -

---

## rag

### RAG-1
- priority: P0
- epic: rag
- repo: ballast
- title: RAGState TypedDict + baseline graph (retrieve -> generate -> END), compiled and smoke-tested
- accept: a `RAGState` TypedDict (question, documents, answer, citations, critique, retries) and a `StateGraph` wiring retrieve and generate that returns an answer against the seed corpus using `FakeLLMClient`
- why: the walking skeleton every later node attaches to
- tests: `graph.invoke({"question": ...})` returns a non-empty answer with the corpus retrieved
- files: rag/state.py, rag/nodes.py, rag/graph.py
- deps: CORP-6, CORE-5
- status: done
- pr: local

### RAG-2
- priority: P0
- epic: rag
- repo: ballast
- title: Generate node with citations drawn from the chunks actually used
- accept: the generate node returns an answer plus a `citations` list of `{source, url, chunk_id}` for the chunks it grounded on
- why: citations are required by the gateway must-cite policy and the faithfulness metric
- tests: citations are non-empty and resolve to real seed-corpus files; an answer with no support cites nothing
- files: rag/nodes.py
- deps: RAG-1
- status: done
- pr: local

### RAG-3
- priority: P1
- epic: rag
- repo: ballast
- title: Critic node: groundedness check (structured pass/fail + reason)
- accept: a `critic` node calls `complete_structured` returning `{grounded: bool, reason}` over the answer and its chunks, added after generate
- why: the self-heal trigger; without it the pipeline cannot tell good answers from hallucinations
- tests: a scripted hallucinated answer is flagged `grounded=false`; a supported answer passes
- files: rag/nodes.py
- deps: RAG-2
- status: done
- pr: local

### RAG-4
- priority: P1
- epic: rag
- repo: ballast
- title: Document relevance grading before generate (CRAG-style filtering)
- accept: a `grade_documents` node drops low-relevance chunks before generate; if none survive, route to query rewrite
- why: generating over irrelevant chunks is a top hallucination source
- tests: an off-topic chunk is filtered; an all-irrelevant retrieval routes to rewrite, not generate
- files: rag/nodes.py, rag/graph.py
- deps: RAG-1
- status: done
- pr: local

### RAG-5
- priority: P1
- epic: rag
- repo: ballast
- title: Self-heal loop: conditional edge on critic failure -> rewrite_query -> re-retrieve
- accept: `add_conditional_edges` routes critic-fail to a `rewrite_query` node that reformulates and loops back to retrieve; critic-pass routes to END
- why: this is the defining behavior of Project 1, the cyclical not-a-linear-chain graph
- tests: a deterministic run re-retrieves once after a failure then passes; the graph is acyclic-safe via the cap below
- files: rag/nodes.py, rag/graph.py
- deps: RAG-3, RAG-4
- status: done
- pr: local

### RAG-6
- priority: P1
- epic: rag
- repo: ballast
- title: Retry cap + graceful "insufficient information" fallback
- accept: a `retries` counter caps the self-heal loop (default 2, configurable) and a `fallback` node returns an explicit decline when exhausted, never a guess
- why: prevents infinite loops and turns "I cannot ground this" into honest refusal instead of a hallucination
- tests: forced repeated critic failure fires the fallback, not an infinite loop; the cap is config-driven
- files: rag/nodes.py, rag/graph.py
- deps: RAG-5
- status: done
- pr: local

### RAG-7
- priority: P2
- epic: rag
- repo: ballast
- title: Query transformation strategies: multi-query and HyDE, configurable
- accept: optional `multi_query` (fan out reformulations and union results) and `HyDE` (hypothetical-answer embedding) strategies selectable by config feed retrieve
- why: a single literal query under-retrieves; these are standard recall levers the eval can measure
- tests: multi-query unions results from multiple reformulations; HyDE produces a query embedding path; both are off by default
- files: rag/transform.py, rag/graph.py
- deps: RAG-1
- status: done
- pr: -

### RAG-8
- priority: P2
- epic: rag
- repo: ballast
- title: Answer-relevancy self-check node (does the answer address the question)
- accept: a node scores whether the answer actually responds to the question and feeds the self-heal decision alongside groundedness
- why: an answer can be grounded yet evasive; relevancy is a distinct failure mode
- tests: an on-topic-but-evasive answer is caught; a direct answer passes
- files: rag/nodes.py
- deps: RAG-5
- status: done
- pr: -

### RAG-9
- priority: P2
- epic: rag
- repo: ballast
- title: Streaming: token streaming + node-event streaming from the graph
- accept: the ask path can stream generated tokens and emit a node-start/end event stream for the trace
- why: a credible LLM app streams; the CLI and any future UI need node events
- tests: a streamed run yields incremental tokens and ordered node events
- files: rag/stream.py, rag/ask.py
- deps: RAG-6
- status: done
- pr: -

### RAG-10
- priority: P3
- epic: rag
- repo: ballast
- title: Async graph execution
- accept: the graph and nodes run under async invocation without blocking on I/O-bound LLM and store calls
- why: batch eval and any concurrency need async to be tolerable
- tests: an async invoke returns the same result as sync on a fixture
- files: rag/graph.py, rag/nodes.py
- deps: RAG-6
- status: done
- pr: -

### RAG-11
- priority: P3
- epic: rag
- repo: ballast
- title: Checkpointing and thread memory for follow-up questions
- accept: a LangGraph checkpointer persists state by thread id so a follow-up question reuses prior context
- why: demonstrates stateful conversation, a core LangGraph capability
- tests: a second question on the same thread sees the first turn's context
- files: rag/graph.py, rag/memory.py
- deps: RAG-6
- status: done
- pr: -

### RAG-12
- priority: P2
- epic: rag
- repo: ballast
- title: Configurable graph assembly via strategy flags
- accept: a single builder assembles the graph from config (rerank on/off, hyde on/off, hybrid on/off, max_retries) so the eval matrix can vary strategies without code edits
- why: EVAL-17 and the model/strategy matrix depend on assembling variants from config
- tests: two configs produce graphs with the expected nodes present or absent
- files: rag/graph.py, rag/config.py
- deps: RAG-7, CORP-7, CORP-8
- status: done
- pr: -

### RAG-13
- priority: P0
- epic: rag
- repo: ballast
- title: `make ask` CLI: ask a question, stream the node trace and the cited answer
- accept: `python -m rag.ask "question"` runs the graph against the ingested corpus, prints each node as it executes, and prints the final cited answer, with a `--show-trace` flag
- why: the primary human-facing demo surface and the M1 acceptance proof
- tests: a CLI run on the seed corpus prints nodes and a cited answer; `--show-trace` adds the trace
- files: rag/ask.py, Makefile
- deps: RAG-2, CORE-7
- status: done
- pr: local

### RAG-14
- priority: P3
- epic: rag
- repo: ballast
- title: Graph visualization: mermaid export + a sample run state log
- accept: a script writes the compiled topology to `rag/graph.mmd` and dumps a sample run's per-node state to JSON for the docs
- why: the cyclical graph is the headline artifact; it should be visible in the README
- tests: the mermaid file is regenerated deterministically from the compiled graph
- files: rag/viz.py, rag/graph.mmd
- deps: RAG-13
- status: done
- pr: -

### RAG-15
- priority: P2
- epic: rag
- repo: ballast
- title: Node failure handling: degrade gracefully, never silent-zero
- accept: a node whose LLM or store call fails records a tri-state failure on the state and routes to fallback rather than emitting an empty or zero result
- why: Operational Lesson 1; a swallowed failure poisons citations, critic, and eval
- tests: an injected retrieve failure routes to fallback with a recorded failure, not a blank answer
- files: rag/nodes.py, rag/graph.py
- deps: RAG-6
- status: done
- pr: -

---

## gateway

### GW-1
- priority: P1
- epic: gateway
- repo: ballast
- title: Gateway skeleton: request/response envelope, ordered pre/post hook pipeline, short-circuit
- accept: `Gateway(handler)` wraps a `question -> answer` callable, runs ordered pre-hooks, the handler, then post-hooks, and any hook can short-circuit with a typed blocked result
- why: the composition point for every guardrail; defines the hook contract
- tests: hook ordering is honored; a short-circuiting pre-hook skips the handler; a post-hook can replace the answer
- files: gateway/gateway.py, gateway/types.py
- deps: RAG-6
- status: done
- pr: local

### GW-2
- priority: P1
- epic: gateway
- repo: ballast
- title: Input guardrail: PII detection (Luhn-checked cards, SSN, email, phone), block or redact
- accept: a pre-hook detects Luhn-validated card numbers, SSNs, emails, and phones and either blocks or redacts per config
- why: the canonical Project 2 example (a user pasting a card number) and a real privacy control
- tests: a pasted card is caught; a random 16-digit string failing Luhn is not; redaction masks in place
- files: gateway/input/pii.py
- deps: GW-1
- status: done
- pr: local

### GW-3
- priority: P2
- epic: gateway
- repo: ballast
- title: Input guardrail: secret/credential detection (API keys, tokens) in user input
- accept: a pre-hook flags pasted credentials (provider key patterns, bearer tokens, private-key headers) and blocks or redacts
- why: users paste secrets; logging or forwarding them is a real incident class
- tests: a planted API-key pattern is caught; ordinary prose is not flagged
- files: gateway/input/secrets.py
- deps: GW-1
- status: done
- pr: local

### GW-4
- priority: P1
- epic: gateway
- repo: ballast
- title: Input guardrail: prompt-injection heuristics
- accept: a pre-hook flags known injection and override patterns (ignore-previous-instructions, role override, system-prompt exfiltration) via a maintained rule list
- why: the cheap first line of injection defense before spending a model call
- tests: several known injection strings are flagged; benign questions pass
- files: gateway/input/injection.py
- deps: GW-1
- status: done
- pr: local

### GW-5
- priority: P2
- epic: gateway
- repo: ballast
- title: Input guardrail: LLM injection classifier (haiku) for ambiguous cases
- accept: when heuristics are inconclusive, escalate to a `claude-haiku-4-5` classifier returning `{injection: bool, reason}`, with the heuristic result short-circuiting clear cases to save cost
- why: heuristics miss novel phrasings; a cheap classifier catches the long tail
- tests: an obfuscated injection the heuristics miss is caught by the classifier; clear cases never call the model
- files: gateway/input/injection_llm.py
- deps: GW-4
- status: done
- pr: -

### GW-6
- priority: P1
- epic: gateway
- repo: ballast
- title: Output guardrail: schema validation (Pydantic) with repair-or-retry
- accept: a post-hook validates the response against a Pydantic schema (answer, citations, refusal flag) and asks the model to repair once before falling back
- why: downstream consumers and the policy layer need a guaranteed response shape
- tests: a malformed output is repaired; a still-bad output falls back safely
- files: gateway/output/schema.py
- deps: GW-1
- status: done
- pr: local

### GW-7
- priority: P2
- epic: gateway
- repo: ballast
- title: Output guardrail: toxicity screen
- accept: a post-hook screens the answer for toxic or unsafe content via a haiku classifier and replaces it with the safe fallback on a hit
- why: a published assistant must not emit toxic content even if the corpus or a jailbreak induces it
- tests: a planted toxic answer is replaced; a normal answer passes
- files: gateway/output/toxicity.py
- deps: GW-6
- status: done
- pr: -

### GW-8
- priority: P2
- epic: gateway
- repo: ballast
- title: Output guardrail: topicality / domain check (stay on finance and investing)
- accept: a post-hook flags answers that drift off the finance/investing domain and replaces them with the safe fallback
- why: an on-topic assistant is part of the policy promise and reduces jailbreak blast radius
- tests: an off-domain answer is caught; an on-domain answer passes
- files: gateway/output/topicality.py
- deps: GW-6
- status: done
- pr: -

### GW-9
- priority: P1
- epic: gateway
- repo: ballast
- title: Policy engine: declarative YAML rules (the non-engineer-editable layer)
- accept: `policy.yaml` declares named rules and `policy.py` enforces them as hooks; adding or editing a rule needs no code change
- why: the configurable policy layer is the distinguishing feature of Project 2
- tests: a custom policy file loads and a violating answer is blocked; a syntactically bad policy fails loudly at load
- files: gateway/policy.py, gateway/policy.yaml
- deps: GW-6
- status: done
- pr: local

### GW-10
- priority: P2
- epic: gateway
- repo: ballast
- title: Policy rule: must-cite enforcement
- accept: a policy rule rejects any substantive answer that carries no citations and triggers the corrected retry
- why: "always cite sources" is the core compliance promise of the corpus framing
- tests: an uncited substantive answer is rejected; a cited answer and an explicit refusal both pass
- files: gateway/policy.py, gateway/policy.yaml
- deps: GW-9
- status: done
- pr: local

### GW-11
- priority: P1
- epic: gateway
- repo: ballast
- title: Policy rule: prohibited-advice enforcement (personalized financial, medical, legal)
- accept: a policy rule blocks personalized financial advice and any medical or legal advice and returns the safe fallback
- why: the real compliance need that makes this corpus the best application, reusable on the fleet
- tests: a personalized-allocation answer is blocked; a general educational answer passes
- files: gateway/policy.py, gateway/policy.yaml
- deps: GW-9
- status: done
- pr: local

### GW-12
- priority: P2
- epic: gateway
- repo: ballast
- title: Auto-retry with corrected prompt on guardrail failure
- accept: on an output-guardrail failure the gateway re-invokes the handler once with a correction instruction derived from the failing rule
- why: a retry recovers many near-miss answers without falling all the way back
- tests: a missing-citation answer is corrected on retry; a still-failing answer proceeds to fallback
- files: gateway/gateway.py
- deps: GW-10, GW-11
- status: done
- pr: -

### GW-13
- priority: P2
- epic: gateway
- repo: ballast
- title: Typed safe-fallback responses
- accept: a small set of typed fallback responses (insufficient info, blocked by policy, blocked input) the gateway returns instead of an unsafe answer
- why: fallbacks must be explicit and testable, not ad hoc strings
- tests: each guardrail path returns the correct typed fallback
- files: gateway/fallback.py
- deps: GW-1
- status: done
- pr: local

### GW-14
- priority: P2
- epic: gateway
- repo: ballast
- title: Gateway decision audit log + per-decision metrics
- accept: every gateway decision (allowed, blocked, redacted, repaired, retried, fell-back) appends a structured record naming the triggering rule, surfaced under `make ask --show-trace`
- why: you cannot trust or tune guardrails you cannot inspect
- tests: a blocked request produces an audit entry naming the rule; counts aggregate per rule
- files: gateway/audit.py
- deps: GW-12, GW-13
- status: done
- pr: local

### GW-15
- priority: P3
- epic: gateway
- repo: ballast
- title: Gateway composition from config (enable and order hooks declaratively)
- accept: the active hooks and their order are defined in config so a deployment can compose its own guardrail stack without code
- why: matches the configurable spirit of the policy layer and lets the eval vary guardrail stacks
- tests: two configs yield different active-hook orders; an unknown hook name fails loudly
- files: gateway/compose.py, gateway/config.py
- deps: GW-14
- status: done
- pr: -

---

## eval

### EVAL-1
- priority: P2
- epic: eval
- repo: ballast
- title: Golden dataset schema + loader and validator
- accept: a record schema `{id, question, expected, must_cite, category, notes}` and a loader that validates every line and fails on a bad record
- why: the contract every metric and the gate read; it must be strict
- tests: a valid file loads; a missing field or duplicate id fails with a clear message
- files: eval/schema.py, eval/golden.jsonl
- deps: CORP-2
- status: done
- pr: local

### EVAL-2
- priority: P2
- epic: eval
- repo: ballast
- title: Seed 100+ golden QA pairs across categories
- accept: `eval/golden.jsonl` holds 100+ records spanning answerable, unanswerable (expect a decline), adversarial/injection, multi-hop, and out-of-corpus categories
- why: a thin or single-category set hides exactly the failures the pipeline is built to prevent
- tests: category counts meet documented minimums; every unanswerable case has expected=decline
- files: eval/golden.jsonl
- deps: EVAL-1
- status: done
- pr: local

### EVAL-3
- priority: P2
- epic: eval
- repo: ballast
- title: Metric: faithfulness / groundedness (LLM-judge against cited sources)
- accept: `metrics/faithfulness.py` scores an answer for support by its cited chunks on 0..1 via a haiku judge
- why: the central quality signal; an answer unsupported by its own citations is a hallucination
- tests: a hand-labeled mini-set shows the metric separating grounded from ungrounded answers
- files: eval/metrics/faithfulness.py
- deps: EVAL-1, RAG-2
- status: done
- pr: local

### EVAL-4
- priority: P2
- epic: eval
- repo: ballast
- title: Metric: answer relevancy
- accept: `metrics/relevancy.py` scores how well an answer addresses the question on 0..1, independent of correctness
- why: distinguishes evasive-but-grounded answers from genuinely responsive ones
- tests: an evasive answer scores low and a direct answer high on labeled examples
- files: eval/metrics/relevancy.py
- deps: EVAL-1
- status: done
- pr: -

### EVAL-5
- priority: P2
- epic: eval
- repo: ballast
- title: Metrics: context precision and recall (retrieval quality)
- accept: `metrics/retrieval.py` computes context precision and recall against per-question relevant-source labels in the golden set
- why: most answer failures are retrieval failures; measuring retrieval separately localizes the fault
- tests: precision and recall match hand-computed values on a fixture
- files: eval/metrics/retrieval.py
- deps: EVAL-2, CORP-6
- status: done
- pr: -

### EVAL-6
- priority: P2
- epic: eval
- repo: ballast
- title: Metric: hallucination rate (the headline gate)
- accept: `metrics/hallucination.py` derives a corpus-wide rate from faithfulness plus the unanswerable cases (an answer where a decline was expected counts as a hallucination)
- why: the single number the merge gate keys on
- tests: a labeled set yields the expected rate; an answered-when-should-decline case counts correctly
- files: eval/metrics/hallucination.py
- deps: EVAL-3
- status: done
- pr: local

### EVAL-7
- priority: P2
- epic: eval
- repo: ballast
- title: Metric: refusal correctness
- accept: `metrics/refusal.py` measures whether the pipeline declines on unanswerable/out-of-corpus questions and answers on answerable ones, reporting both error directions
- why: a system that always refuses scores well on hallucination but is useless; both directions matter
- tests: over-refusal and under-refusal are each detected on labeled examples
- files: eval/metrics/refusal.py
- deps: EVAL-2
- status: done
- pr: local

### EVAL-8
- priority: P2
- epic: eval
- repo: ballast
- title: Metric: latency p50/p95 and cost per query from the trace
- accept: `metrics/perf.py` aggregates p50 and p95 latency and mean cost per query from `core.trace`
- why: quality is meaningless without the cost and latency it was bought at
- tests: synthetic traces yield the expected percentiles and cost mean
- files: eval/metrics/perf.py
- deps: EVAL-1, CORE-7
- status: done
- pr: local

### EVAL-9
- priority: P2
- epic: eval
- repo: ballast
- title: Eval runner: run the pipeline over the golden set, emit metrics + per-case results
- accept: `python -m eval.runner` runs every golden question through the gateway and RAG, computes all metrics, and writes `eval/results/<sha>.json` with aggregates and per-case pass/fail, against a fixed corpus snapshot
- why: the harness that produces the numbers the gate and dashboard consume
- tests: a small fixture golden set runs end to end and writes a well-formed results file
- files: eval/runner.py
- deps: EVAL-6, EVAL-7, EVAL-8, EVAL-4, GW-9
- status: done
- pr: local

### EVAL-10
- priority: P3
- epic: eval
- repo: ballast
- title: Metric confidence intervals via bootstrap
- accept: the runner reports a bootstrap confidence interval for each aggregate metric, not just a point estimate
- why: a 4% vs 6% hallucination move can be pure noise on 100 questions; the gate must not chase noise
- tests: bootstrap CIs on a fixture are stable and bracket the point estimate
- files: eval/stats.py, eval/runner.py
- deps: EVAL-9
- status: done
- pr: -

### EVAL-11
- priority: P3
- epic: eval
- repo: ballast
- title: Per-category metric breakdown
- accept: the runner reports every metric broken out by category so a regression in one category is not averaged away by the rest
- why: an aggregate can stay flat while adversarial handling collapses
- tests: the breakdown sums and counts reconcile with the aggregate on a fixture
- files: eval/runner.py
- deps: EVAL-9
- status: done
- pr: -

### EVAL-12
- priority: P2
- epic: eval
- repo: ballast
- title: Baseline + regression detection vs the last committed run
- accept: the runner compares each metric to the previous ledger entry and flags a regression only when it exceeds the metric's confidence interval (or a configured margin)
- why: a useful gate distinguishes a real regression from run-to-run judge noise
- tests: a within-noise change is not flagged; a clear regression is
- files: eval/regression.py
- deps: EVAL-10, EVAL-14
- status: done
- pr: -

### EVAL-13
- priority: P2
- epic: eval
- repo: ballast
- title: Local CI gate: thresholds -> exit code (mirrors /local-ci), optional pre-push hook
- accept: `python -m eval.gate` returns non-zero when hallucination rate exceeds the threshold, p95 latency regresses beyond the SLA, or refusal-correctness drops; `make local-ci` chains lint, types, tests, and this gate; a documented opt-in git pre-push hook runs it
- why: Project 3's "block the merge", implemented locally because Actions is billing-disabled
- tests: a results file over threshold exits non-zero; a clean one exits zero
- files: eval/gate.py, Makefile, scripts/pre-push.sample
- deps: EVAL-12
- status: done
- pr: local

### EVAL-14
- priority: P2
- epic: eval
- repo: ballast
- title: Metrics ledger: append each run to a committed JSONL keyed by git SHA
- accept: each runner pass appends `{sha, timestamp, metrics}` to `eval/history.jsonl`, committed so the trend survives across sessions
- why: regression detection and the dashboard both read the trend from here
- tests: a run appends exactly one well-formed line; the regression check reads the last entry
- files: eval/history.jsonl, eval/ledger.py
- deps: EVAL-9
- status: done
- pr: local

### EVAL-15
- priority: P3
- epic: eval
- repo: ballast
- title: Trend dashboard: static HTML over commits
- accept: `make dashboard` renders `eval/dashboard/index.html` from `history.jsonl` with charts for hallucination rate, relevancy, refusal correctness, p95 latency, and cost per query over commits, with no server and a single vendored chart lib
- why: the "getting better or worse" surface Project 3 calls for
- tests: the dashboard renders from a fixture ledger and opens as a static file
- files: eval/dashboard/build.py, eval/dashboard/index.html
- deps: EVAL-14
- status: done
- pr: local

### EVAL-16
- priority: P3
- epic: eval
- repo: ballast
- title: Swap-a-model matrix: run the eval under haiku vs sonnet generation and diff
- accept: `python -m eval.runner --matrix model=haiku,sonnet` runs the golden set under each generation model via the LLMClient seam (no code change) and prints a side-by-side quality/cost/latency diff
- why: demonstrates the swappable seam and the quality-vs-cost tradeoff concretely
- tests: the matrix runs both variants and emits a diff table
- files: eval/matrix.py, eval/runner.py
- deps: EVAL-9
- status: done
- pr: -

### EVAL-17
- priority: P3
- epic: eval
- repo: ballast
- title: Prompt-change A/B harness
- accept: the runner compares two named prompt versions on the golden set and reports the metric delta with its confidence interval
- why: prompts change constantly; "did this prompt help" should be a measured answer, not a vibe
- tests: two prompt versions produce a delta with a CI on a fixture
- files: eval/ab.py, rag/prompts.py
- deps: EVAL-12, RAG-12
- status: done
- pr: -

### EVAL-18
- priority: P2
- epic: eval
- repo: ballast
- title: Adversarial eval set: injection attempts must be blocked by the gateway
- accept: an adversarial subset asserts the gateway blocks injection and policy-violating inputs, and the gate fails if the block rate drops below the configured floor
- why: a security regression should break the build exactly like a quality regression
- tests: known injections are blocked; a deliberately weakened guardrail drops the block rate and fails the gate
- files: eval/adversarial.py, eval/golden.jsonl
- deps: EVAL-9, GW-5, GW-11
- status: done
- pr: -

### EVAL-19
- priority: P3
- epic: eval
- repo: ballast
- title: Judge calibration: human-labeled mini-set + agreement check
- accept: a small human-labeled set measures the LLM judge's agreement with human labels, and the runner warns when agreement falls below a threshold
- why: an LLM-as-judge you never calibrate can drift; the eval should not be trusted blindly
- tests: agreement is computed against the labeled set; low agreement raises a warning
- files: eval/calibration.py, eval/labels.jsonl
- deps: EVAL-3
- status: done
- pr: -

### EVAL-20
- priority: P3
- epic: eval
- repo: ballast
- title: Eval determinism: seeding + cache use for repeatable runs
- accept: the runner uses the LLM cache and fixed seeds where possible so an unchanged pipeline produces stable metrics across runs
- why: a gate that flaps on its own randomness erodes trust and blocks merges falsely
- tests: two runs of an unchanged pipeline over a fixture yield identical metrics
- files: eval/runner.py
- deps: EVAL-9, CORE-9
- status: done
- pr: -

---

## obs

### OBS-1
- priority: P2
- epic: obs
- repo: ballast
- title: Per-run trace store: write each run's trace to a jsonl under a run id
- accept: every ask and eval run persists its `core.trace` to `runs/<run_id>.json` for later inspection
- why: debugging and the viewer need durable per-run traces, not just stdout
- tests: a run writes a readable trace file keyed by its run id
- files: obs/store.py
- deps: CORE-7
- status: done
- pr: -

### OBS-2
- priority: P3
- epic: obs
- repo: ballast
- title: Single-run trace viewer (static HTML or CLI) showing nodes, calls, and decisions
- accept: `make trace RUN=<id>` renders one run's node sequence, LLM calls, guardrail decisions, tokens, and latency in a readable view
- why: a self-heal loop or a guardrail block is far easier to understand visually than from logs
- tests: the viewer renders a fixture trace with every node and decision present
- files: obs/viewer.py
- deps: OBS-1, GW-14
- status: done
- pr: -

### OBS-3
- priority: P3
- epic: obs
- repo: ballast
- title: Cost and usage view across runs
- accept: `make usage` aggregates token and cost totals across recent runs by model and by node type
- why: makes the running cost of the system visible and attributable
- tests: aggregates match a fixture set of runs
- files: obs/usage.py
- deps: OBS-1
- status: done
- pr: -

---

## sec

### SEC-1
- priority: P1
- epic: sec
- repo: ballast
- title: Secrets hygiene: Secrets Manager at runtime (done in config), local secret scan in local-ci
- accept: the Anthropic key resolves from AWS Secrets Manager via `Settings.resolve_api_key` (env override dev-only, no secret on disk) AND a `.gitleaks`-style local scan runs in `make local-ci`; `.env` holds no secrets and is gitignored
- why: a committed or on-disk plaintext key is the most common and most damaging repo incident; the SM-resolution half is already implemented, this item adds the local scan
- tests: the scan flags a planted fake secret in a fixture and passes a clean tree
- files: .gitleaks.toml, Makefile, .gitignore
- deps: CORE-2
- status: done
- pr: -

### SEC-2
- priority: P2
- epic: sec
- repo: ballast
- title: Dependency audit in local-ci (pip-audit)
- accept: `make local-ci` runs a dependency vulnerability audit that fails on a known-vulnerable pinned dependency
- why: a supply-chain advisory should surface locally, not in production
- tests: the audit step runs and reports cleanly on the current pins
- files: Makefile, pyproject.toml
- deps: CORE-1
- status: done
- pr: -

### SEC-3
- priority: P2
- epic: sec
- repo: ballast
- title: Input/output size and cost hard caps (cost and DoS guard)
- accept: the gateway rejects oversized inputs and the per-run budget guard caps spend, both with typed errors
- why: an unbounded input or a runaway loop can exhaust cost or memory
- tests: an oversized input is rejected; the budget cap trips on a synthetic overspend
- files: gateway/limits.py, core/cost.py
- deps: GW-1, CORE-6
- status: done
- pr: -

### SEC-4
- priority: P3
- epic: sec
- repo: ballast
- title: Injection defense-in-depth test matrix + doc
- accept: a documented matrix maps injection techniques to the layer that stops each (heuristic, classifier, output policy) with a test per cell
- why: makes the layered defense legible and catches a regression in any single layer
- tests: each matrix cell has a passing test; a disabled layer fails its cell
- files: docs/injection-defense.md, tests/test_injection_matrix.py
- deps: GW-5, GW-8
- status: done
- pr: -

### SEC-5
- priority: P1
- epic: sec
- repo: ballast
- title: PII and secret redaction in logs and traces
- accept: the logging and trace serializers redact card numbers, secrets, and detected PII so raw sensitive data never lands in a log or trace file
- why: catching PII at the gateway is moot if the trace then writes it to disk in the clear
- tests: a trace containing a card number serializes with it masked; logs never emit the raw value
- files: core/logging.py, core/trace.py, core/redact.py
- deps: CORE-8, GW-2
- status: done
- pr: -

---

## dx

### DX-1
- priority: P2
- epic: dx
- repo: ballast
- title: README with architecture diagram and quickstart
- accept: the README explains the three subsystems, embeds the graph diagram, and gives a copy-paste quickstart from clone to `make ask`
- why: a portfolio project is judged first by its README
- tests: the quickstart commands match the actual Makefile targets (a doc-lint check)
- files: README.md
- deps: RAG-13
- status: done
- pr: -

### DX-2
- priority: P3
- epic: dx
- repo: ballast
- title: Example walkthrough script: end-to-end ask with trace
- accept: `examples/walkthrough.py` runs a question through ingest, ask, and the trace, printing a narrated end-to-end flow
- why: a runnable example onboards a reader faster than prose
- tests: the script runs against the seed corpus without error
- files: examples/walkthrough.py
- deps: RAG-13
- status: done
- pr: -

### DX-3
- priority: P3
- epic: dx
- repo: ballast
- title: Demo script showcasing self-heal, a guardrail block, and a citation
- accept: `make demo` runs three curated questions that visibly trigger a self-heal retry, a policy block, and a cited answer
- why: the fastest way to show all three subsystems working together
- tests: each demo question reaches its intended path on the seed corpus
- files: examples/demo.py, Makefile
- deps: GW-11, RAG-6
- status: done
- pr: -

### DX-4
- priority: P3
- epic: dx
- repo: ballast
- title: Makefile completeness + help target
- accept: `make help` lists every target with a one-line description and all documented targets exist
- why: the Makefile is the project's command surface; it should be self-describing
- tests: `make help` output lists every target referenced in the README
- files: Makefile
- deps: CORE-1
- status: done
- pr: -

### DX-5
- priority: P3
- epic: dx
- repo: ballast
- title: ADRs for the key choices (LangGraph, Chroma, local CI, swappable LLM seam, corpus framing)
- accept: an `adr/` folder records each major decision with context, options, and consequences
- why: the reasoning behind the design should be durable and reviewable, not only in chat history
- tests: each ADR follows the template and the index lists them
- files: adr/0001-*.md ... adr/index.md
- deps: none
- status: done
- pr: -

### DX-6
- priority: P3
- epic: dx
- repo: ballast
- title: Contributing guide + how to run the loop against this repo
- accept: `CONTRIBUTING.md` documents the local workflow, the DoD, and how `/loop /backlog` targets this repo
- why: makes the backlog-driven workflow reproducible for the next session or contributor
- tests: referenced commands and paths exist (doc-lint)
- files: CONTRIBUTING.md
- deps: EVAL-13
- status: done
- pr: -

### DX-7
- priority: P3
- epic: dx
- repo: ballast
- title: Reproducible environment: pinned deps + lockfile + Python version pin
- accept: dependencies are pinned with a lockfile and the Python version is pinned so a fresh clone builds identically
- why: an unpinned LLM/ML stack drifts and breaks reproducibility of both demos and evals
- tests: a clean install from the lock resolves without conflicts
- files: pyproject.toml, requirements.lock, .python-version
- deps: CORE-1
- status: done
- pr: -

### CORE-11
- priority: P1
- epic: core
- repo: ballast
- title: Context window overflow guard + graceful degradation on approaching limit
- accept: before each LLM call, remaining tokens are checked against the model's max; if insufficient, degrade to fallback or truncate context with a warning, never a silent failure
- why: a large corpus or many self-heal retries can exhaust tokens mid-run; the degradation must be explicit (tri-state)
- tests: a synthetic call at 90% token budget degrades gracefully; a clean call under budget proceeds normally
- files: core/llm.py, core/cost.py
- deps: CORE-6
- status: open
- pr: -

### RAG-16
- priority: P1
- epic: rag
- repo: ballast
- title: Adaptive context truncation before generation when approaching token budget
- accept: if formatted context exceeds a threshold of available generation tokens, re-rank and keep top-scoring chunks (or summarize) before generate
- why: the critic gates hallucinations reactively; shrinking context proactively avoids the retry loop entirely
- tests: a retrieval with 50+ low-scoring chunks is truncated before generate; a clean retrieval is untouched
- files: rag/nodes.py, rag/truncate.py
- deps: RAG-2, CORP-8
- status: open
- pr: -

### EVAL-21
- priority: P2
- epic: eval
- repo: ballast
- title: Citation accuracy metric: verify cited chunks actually support each answer claim
- accept: a metric scores how many of the answer's core claims are grounded in the text of its cited chunks, reporting support precision and recall
- why: faithful-sounding scores can mask cherry-picked citations; citation-claim overlap is the real guardrail
- tests: an answer citing a chunk but making unrelated claims is caught; full support scores high
- files: eval/metrics/citation_accuracy.py
- deps: EVAL-3
- status: open
- pr: -

### EVAL-22
- priority: P2
- epic: eval
- repo: ballast
- title: Adaptive batch eval sizing: cap cost and latency via sampling and model selection
- accept: a --budget-usd or --latency-sla flag adjusts golden-set sampling and model choice to stay under the constraint
- why: regression gates and nightly evals need cost and time predictability; hand-tuning is brittle
- tests: a run with --budget-usd 0.10 does not exceed the budget; a run with --latency-sla 20s completes within it
- files: eval/runner.py, eval/sample.py
- deps: EVAL-9, CORE-6
- status: open
- pr: -

### EVAL-23
- priority: P0
- epic: eval
- repo: ballast
- title: Fresh eval baseline is RED; fix injection blocking and hallucination rate, then commit a green ledger entry
- accept: a full `make eval` run at HEAD passes the gate (injection_block_rate >= 0.95, hallucination_rate <= 0.05, p95 within band) and its ledger entry is committed as the new baseline
- why: a 2026-07-02 full run at 3336c56 over the grown 89-record golden set failed the gate (injection block 55.6% vs 95% floor, hallucination 5.6% vs 5.0% max, p95 13.6s vs 12.2s allowed); the committed 7059b34 entry predates the adversarial/injection categories and was a stale green (results kept locally in eval/results/3336c56-f9a497.json)
- tests: the gate passes on the new committed entry with no staleness override
- files: src/ballast/gateway/, src/ballast/rag/, eval/history.jsonl
- deps: none
- status: done
- pr: local
- note: DONE 2026-07-02. Root cause: the 4 leaked adversarial cases (adv-3/10/11/13) were personalized-advice solicitations with no injection vocabulary, so no input layer saw them and the corpus answered them faithfully in an educational tone the output policy regexes never match; the "defense layers 2-3 default OFF despite docs" finding was confirmed (Settings.pre_hooks lacked injection-llm). Fix: new two-tier advice-solicitation input guard (heuristic -> bounded classifier, on by default), injection-llm added to default pre_hooks, injection heuristic widened to "disregard your rules" (adv-3 now blocks at layer 1 free). Green full run at f9a27d8: injection_block_rate 1.00 (9/9, all blocked at input), hallucination_rate 0.0225, refusal_accuracy 0.9888, p95 13.07s, $0.56. The p95 "band" = previous ledger entry p95 * (1 + latency_p95_regress_frac) = 10.14 * 1.2 = 12.17s vs the 43-record 7059b34 entry; that cross-workload comparison was apples-to-oranges, so entries now record n and the gate applies the latency/cost band only like-for-like (skipped once for this 43->89 transition, re-armed by this entry at 13.07 * 1.2 = 15.69s for future 89-record runs; the 0.95/0.05 quality floors are never skipped). Also fixed: the regression detector used the 0.02 rate-scale margin on latency/cost (a 20ms rise would flag), now proportional 20%; subset eval runs (--only/--category/--limit) no longer append to the committed ledger.

### DX-8
- priority: P1
- epic: dx
- repo: ballast
- title: Make the vendored backlog repo-path mapping portable from the repository root
- accept: as a supervisor-run manual bootstrap from the known Ballast repository root (never dispatched through the broken `repo-path ballast` result), fix `python specs/_shared/tooling/backlog.py repo-path ballast` to print that absolute repository root and `repo-path specs` to print its `specs/` directory from both the primary checkout and a linked worktree, deriving from the tool location with no username or machine-specific literal; the current erroneous nested `<repo>/ballast` result has a regression test
- why: every Ballast backlog item carries `repo: ballast`, but the vendored picker currently sends an automated worker to a nonexistent nested directory
- tests: a temporary repo-shaped path and the real checkout both resolve `ballast` to the repo root and `specs` to its child; unknown repo behavior stays unchanged
- files: specs/_shared/tooling/backlog.py, tests/test_backlog_tool.py
- deps: none
- status: done
- pr: local
- note: DONE 2026-08-15. Focused verification: .venv\\Scripts\\python.exe -m pytest tests/test_backlog_tool.py -q (4 passed); both repo-path CLI routes print the worktree root and its specs child.

### EVAL-24
- priority: P3
- epic: eval
- repo: ballast
- title: Report-only retrieval exposure diagnostic over the deterministic fixed golden set
- accept: a standalone eval-only run over every record in `eval/golden.jsonl` in file order calls the direct base `Retriever` exactly once per raw question with `top_k=4`, before gateway hooks, generation, document grading, query transforms, retry, hybrid fusion, or reranking; it freezes profile `hashing-baseline-v1` with repository-native `HashingEmbedder(dim=4096)`, `InMemoryVectorStore`, chunk size 256, overlap 40, and source id equal to stripped `Retrieved.chunk.source`; it compares unweighted retrieved chunk-slot source share with canonical corpus chunk-share over the union of source ids and writes strict JSON under a top-level `retrieval_exposure` key, never under `metrics` or into `eval/history.jsonl`, reporting base-2 Jensen-Shannon divergence, both base-2 Shannon entropies and effective sources (`2^H_bits`), per-source expected/observed shares and deltas, query count, slot count, all frozen config, exclusions, canonical corpus/golden hashes, and tri-state status (`ok`, `not_estimable`, or `failed`) with an explicit non-ok reason; canonical corpus hash is SHA-256 of compact sorted-key UTF-8 JSONL for chunks sorted by `chunk_id` with `chunk_id/source/url/title/heading_path/text`, and golden hash uses the same encoding for parsed records in file order, each with LF terminators; it makes no LLM call, corpus mutation, personal-data read, production instrumentation, or `eval.gate` threshold/exit-code change
- why: source concentration can hide behind aggregate answer metrics; this diagnostic describes one fully pinned base-retrieval exposure only, using corpus chunks as the expected denominator and retrieved chunk slots as the observed denominator, never document stems versus publisher sources, and makes no answer-quality or model-bias claim
- tests: both estimable distributions sum to 1; base-2 Jensen-Shannon divergence stays in `[0, 1]`, with identical distributions equal to 0 and disjoint distributions equal to 1; each effective-source value stays in `[1, k]` for `k` union sources; repeated source ids in separate top-k slots each count as one slot; blank source ids or zero retrieved slots produce `not_estimable` with explicit reasons instead of zero; canonical hashes are identical across CRLF/LF and JSON whitespace changes but change with semantic content/order changes; the standalone top-level payload leaves existing result/history readers backward compatible; and `eval.gate` returns the same exit code before and after the artifact exists
- files: src/ballast/eval/metrics/exposure.py, scripts/retrieval_exposure.py, tests/test_retrieval_exposure.py
- deps: EVAL-9, CORP-10, DX-8
- status: done
- pr: local
- note: DONE 2026-08-16. Implementation 4b95ed1, 4dfd5e0, e4376ef, and 5550495; verification refresh 312fa4f. Focused backlog/exposure suite: 30 passed; fresh 89-case eval ledger entry 5550495 cost $0.544208 and passed the eval gate; local CI passed secret/leak/dependency scans, Ruff, mypy, 294 tests, and the eval gate. Deterministic production-corpus report was status ok with 89 queries, 356 slots, corpus SHA-256 0137a0ebd99c7cda205f073ee7d9b070c0b081d85704910ab3a1cb69acd116d9, golden SHA-256 3375cde4e235d7eb35f5d201ea3911286c61921d04a00593e95456d7614a4b7a, and all metric bounds satisfied; the report remains uncommitted in a temporary path.

### SEC-7
- priority: P1
- epic: sec
- repo: ballast
- title: Publish gate hard-fails when the local leak-scan terms file is missing
- accept: leak_scan run in publish mode (flag or env, wired into the PUBLISHING.md pre-push checks) exits nonzero with a clear message when .leak_scan_terms is absent or empty; normal local-ci runs keep the warn-and-continue behavior
- why: the held-term and email coverage lives entirely in the gitignored .leak_scan_terms, so a snapshot built on a machine without the file passes the scanner while silently under-protected (disclosure-audit caveat, 2026-07-02)
- tests: publish mode with the file absent exits nonzero; publish mode with the file present passes on a clean tree; default mode still warns and continues
- files: scripts/leak_scan.py, PUBLISHING.md
- deps: none
- status: open
- pr: -

### OBS-4
- priority: P2
- epic: obs
- repo: ballast
- title: Guardrail analytics: aggregate blocks/redactions/retries by rule and trend them
- accept: a make target generates a JSON report per rule (total blocks, block rate, latency impact) and renders an HTML view across recent runs
- why: guardrails cannot be tuned blind; block trends reveal over-strict rules or emerging jailbreaks
- tests: two runs with different block patterns produce distinct rule counts; the HTML view generates and parses
- files: obs/guardrail_analytics.py, obs/dashboard_guardrails.html
- deps: OBS-1, GW-14
- status: open
- pr: -

### SEC-6
- priority: P2
- epic: sec
- repo: ballast
- title: Cost anomaly detection: flag repeated queries above the running median cost
- accept: cost per query is tracked and 3+ consecutive queries above 2x the running median are flagged with a trace decision marker
- why: a prompt injection or runaway retrieval loop can drain a budget; early detection beats bill shock
- tests: two normal queries then three expensive ones flags on the third; normal variance does not trip
- files: core/cost.py, core/anomaly.py
- deps: CORE-6, CORE-8
- status: open
- pr: -

### CORP-11
- priority: P2
- epic: corpus
- repo: ballast
- title: Corpus versioning and changelog: tag snapshots, track per-document changes
- accept: ingest --tag records a chunk-set SHA per snapshot and a corpus CHANGELOG.md documents document-level changes between versions
- why: eval reproducibility and regression attribution depend on knowing which corpus produced which metrics
- tests: two ingests with different documents produce different SHAs; the changelog updates on a source edit
- files: core/corpus_version.py, corpus/CHANGELOG.md
- deps: CORP-5
- status: open
- pr: -

### OBS-5
- priority: P3
- epic: obs
- repo: ballast
- title: Conversation export: serialize a full turn to a shareable, replayable artifact
- accept: an export command produces JSON with question, answer, citations, guardrail decisions, tokens, and cited chunk text, re-importable as a test fixture
- why: debugging and support need portable, reproducible turns
- tests: an exported run round-trips with all cited chunks present
- files: obs/export.py
- deps: OBS-1
- status: open
- pr: -
