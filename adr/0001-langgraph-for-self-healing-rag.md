# ADR 0001: LangGraph for the self-healing RAG graph

## Status

Accepted

## Context

The core product is not a linear retrieve-then-generate chain. It critiques its own answer and, when
the answer is ungrounded or off-question, rewrites the query and retrieves again, with a retry
counter that caps the loop and a graceful decline when the cap is hit. That is a cyclical, stateful
control flow: conditional branches out of `grade_documents` and `critic`, an edge from
`rewrite_query` back to `retrieve`, and shared mutable state (question, documents, answer, retries,
history) threaded through every node.

## Options

- **Hand-rolled state machine**: a `while` loop over a state dict with `if` branches. Full control,
  no dependency, but the routing logic and the state plumbing become bespoke and easy to get subtly
  wrong (lost updates, missed retry-cap checks), and there is no standard place for checkpointing.
- **A linear chain framework (early LangChain-style)**: simple, but cycles and conditional
  re-entry are awkward to express and the retry loop fights the abstraction.
- **LangGraph**: models the flow as a `StateGraph` with typed state, `add_node`,
  `add_conditional_edges`, and `START`/`END`. Cycles and conditional routing are first-class, and a
  checkpointer gives thread-scoped memory for follow-up questions for free.

## Decision

Use LangGraph. The self-heal loop is a conditional edge plus a `retries` counter in a `TypedDict`
state; the optional checkpointer carries per-thread conversation history.

## Consequences

The graph reads as the data-flow diagram in DESIGN.md, which keeps the self-heal logic legible and
testable node by node. It adds a framework dependency and pins us to its current graph API. The
graph stays decoupled from the model and retriever: nodes take an `LLMClient` and a `RetrieverLike`,
so swapping either (see [ADR 0004](0004-swappable-llm-seam.md)) needs no graph change.
