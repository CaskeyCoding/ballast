"""EVAL-16: model-matrix parsing, orchestration, and diff table (no live model)."""

from __future__ import annotations

from ballast.eval.matrix import MODEL_ALIASES, diff_table, parse_models, run_matrix


def test_parse_models() -> None:
    assert parse_models("model=haiku,sonnet") == ["haiku", "sonnet"]
    assert parse_models("haiku, sonnet ") == ["haiku", "sonnet"]


def test_run_matrix_resolves_aliases() -> None:
    seen: list[str] = []

    def run_one(model_id: str) -> dict[str, float]:
        seen.append(model_id)
        return {"hallucination_rate": 0.0 if "haiku" in model_id else 0.1}

    results = run_matrix(["haiku", "sonnet"], run_one)
    assert seen == [MODEL_ALIASES["haiku"], MODEL_ALIASES["sonnet"]]
    assert results["haiku"]["hallucination_rate"] == 0.0
    assert results["sonnet"]["hallucination_rate"] == 0.1


def test_diff_table_lists_models_and_metrics() -> None:
    results = {
        "haiku": {"hallucination_rate": 0.05, "mean_cost_usd": 0.002},
        "sonnet": {"hallucination_rate": 0.02, "mean_cost_usd": 0.006},
    }
    table = diff_table(results)
    assert "haiku" in table and "sonnet" in table
    assert "hallucination_rate" in table and "mean_cost_usd" in table
