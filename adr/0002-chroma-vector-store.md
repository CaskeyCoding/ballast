# ADR 0002: Chroma as the vector store, behind a VectorStore protocol

## Status

Accepted

## Context

The RAG needs a vector store for similarity search over the chunked corpus. The weekend constraint
is zero extra infra and zero new cloud accounts, but the design also has to stay honest about being
swappable for something heavier later. Tests must run fast and offline with no service to stand up.

## Options

- **In-memory only**: trivially fast for tests, but nothing persists between runs, so `make ingest`
  followed by `make ask` in a fresh process would re-embed every time.
- **pgvector / a hosted vector DB**: production-grade, but needs a running service and credentials,
  which violates the no-infra constraint for the weekend.
- **FAISS**: fast and local, but it is a bare index with no metadata story; we would hand-roll the
  source/title/url metadata and persistence around it.
- **Chroma**: local, file-persistent, carries chunk metadata natively, and needs no service.

## Decision

Use Chroma as the persistent local store, reached through a `VectorStore` protocol with an
`InMemoryStore` as the default for tests and the CLI. `get_store("chroma")` selects the persistent
backend; `get_store("memory")` (the default) keeps tests offline and instant.

## Consequences

Tests and the demo run with no infra and no service process. The `VectorStore` protocol is the seam:
moving to pgvector or a hosted store later is a new implementation of the same three methods, not a
change to ingest or retrieval. The cost is two backends to keep behind one protocol, and Chroma
becomes an optional dependency that mypy treats as untyped (handled with an override).
