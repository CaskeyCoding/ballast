# ballast task surface. The real logic lives in scripts/ so it is portable to
# machines without make (run `python scripts/local_ci.py` directly there).
# More targets (ingest, ask, eval, dashboard, demo) are added as backlog items land.

.PHONY: help install lint typecheck test local-ci ingest corpus-stats ask eval eval-gate \
	eval-matrix calibrate dashboard viz trace usage demo

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Editable install with dev tools
	python -m pip install -e ".[dev]"

lint: ## Ruff lint + format check
	python -m ruff check src tests
	python -m ruff format --check src tests

typecheck: ## mypy
	python -m mypy

test: ## pytest
	python -m pytest

local-ci: ## The merge gate: lint + typecheck + test (+ eval gate once it exists)
	python scripts/local_ci.py

ingest: ## Load corpus/ into the vector store and report a chunk count
	python -m ballast.core.ingest

corpus-stats: ## Report corpus document/chunk counts, size histogram, per-source coverage
	python -m ballast.core.corpus_stats

ask: ## Ask the RAG pipeline a question: make ask Q="what is diversification"
	python -m ballast.rag.ask "$(Q)"

eval: ## Run the eval suite over the golden set (LIMIT=N, ONLY=ids, CATEGORY=cat for a subset)
	python -m ballast.eval.run_cli $(if $(LIMIT),--limit $(LIMIT),) $(if $(ONLY),--only $(ONLY),) \
		$(if $(CATEGORY),--category $(CATEGORY),)

eval-gate: ## Check the latest eval run against thresholds (exit non-zero on regression)
	python -m ballast.eval.gate

eval-matrix: ## Run the eval across generation models: make eval-matrix M=haiku,sonnet
	python -m ballast.eval.matrix --matrix model=$(M) $(if $(LIMIT),--limit $(LIMIT),)

calibrate: ## Measure the faithfulness judge's agreement with the human-labeled set
	python -m ballast.eval.calibration

dashboard: ## Render the metrics trend dashboard from the ledger to eval/dashboard/index.html
	python -m ballast.eval.dashboard

viz: ## Export the RAG graph to rag/graph.mmd and a sample run state log
	python -m ballast.rag.viz

trace: ## View a saved run trace: make trace RUN=<id>
	python -m ballast.obs.viewer $(RUN)

usage: ## Aggregate cost and tokens across saved run traces, by model and node
	python -m ballast.obs.usage

demo: ## Run three curated questions showing a guardrail block, a self-heal retry, and a cited answer
	python examples/demo.py
