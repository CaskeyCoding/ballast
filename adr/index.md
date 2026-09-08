# Architecture Decision Records

The reasoning behind the major design choices, recorded so it is durable and reviewable rather than
living only in chat history. Each record follows [the template](0000-template.md): Status, Context,
Options, Decision, Consequences.

| ADR | Decision |
| --- | --- |
| [0001](0001-langgraph-for-self-healing-rag.md) | LangGraph for the self-healing RAG graph |
| [0002](0002-chroma-vector-store.md) | Chroma as the vector store, behind a VectorStore protocol |
| [0003](0003-local-ci-gate.md) | A local CI gate instead of GitHub Actions |
| [0004](0004-swappable-llm-seam.md) | A swappable LLM seam (LLMClient protocol) |
| [0005](0005-public-methodology-corpus.md) | A public methodology corpus, not private finance data |

To add a decision: copy `0000-template.md` to the next number, fill every section, and add a row
here. `tests/test_adr.py` checks both that each record has all sections and that the index lists it.
