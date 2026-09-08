# ADR 0004: A swappable LLM seam (LLMClient protocol)

## Status

Accepted

## Context

Two goals push on the model boundary. The eval harness has a real "swap a model" requirement: run
the golden set across haiku and sonnet and compare. And every downstream test (graph, gateway,
metrics) needs a deterministic, key-free stand-in or the suite is slow and flaky. Both demand that
nothing outside `core` reach for the anthropic SDK directly.

## Options

- **Call the anthropic SDK at each call site**: least code up front, but it scatters the vendor
  dependency, makes tests need a key or ad-hoc mocking, and makes the model-swap goal a retrofit.
- **A heavy provider-abstraction library**: covers many vendors, but it is far more surface than a
  Claude-first portfolio repo needs, and it still would not give a deterministic test client tuned to
  this code.
- **A thin local `LLMClient` protocol**: one `complete(messages, model, ...)` method, with a
  `ClaudeClient` (lazy-importing the SDK) and a `FakeLLMClient` for tests, plus a `ModelRegistry`
  mapping roles (generation, critic, grader, classifier) to model ids.

## Decision

Define `LLMClient` as a protocol in `core/llm.py`. `ClaudeClient` is the real implementation;
`FakeLLMClient` (scripted by call order or by rule) is the test implementation; the eval matrix
varies the model id through the same protocol. The hard rule: only `core` imports the anthropic SDK.

## Consequences

Tests run offline and deterministically with no key, which is what makes the graph and gateway suites
fast and stable. The model swap is a config change, not code. Cost metering and budget guards wrap
the seam once (`MeteredClient`) and apply to every caller. The cost is the discipline of routing all
calls through the protocol and keeping the registry the single source of model ids.
