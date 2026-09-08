# ADR 0005: A public methodology corpus, not private finance data

## Status

Accepted

## Context

The RAG needs a knowledge base. Two hard constraints frame the choice. A standing privacy rule
forbids personal financial data of any kind from entering a public or demo system. And a synthetic
filler corpus would make the eval golden set and the guardrails policy feel contrived rather than
real.

## Options

- **Synthetic / generic filler text**: zero leak risk, but the eval set is fake, and the guardrails
  policy ("never give personalized advice," "always cite sources") maps to nothing real.
- **Data from a separate private system**: maximally real, but it carries personal financial data,
  and excluding that is non-negotiable.
- **Eric's public, non-sensitive finance and investing methodology** (published methodology and
  public blog content): real and on-brand, with no personal data.

## Decision

The corpus is the public methodology and public blog content only. No personal financial data of
any kind ever enters this repo. The guardrails policy in `policy.yaml` encodes a real compliance
need rather than a toy rule, so it stays reusable beyond this repo.

## Consequences

The eval golden set is genuine investing Q&A and the policy is a real artifact, not a toy. The repo
stays clear of personal financial data entirely, which keeps it safe to treat as a portfolio piece.
The obligation it creates: every corpus addition must be re-checked as public and non-sensitive
before ingest.
