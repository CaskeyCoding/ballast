"""Judge calibration (EVAL-19): measure the LLM judge's agreement with human labels.

An LLM-as-judge you never calibrate can drift. A small hand-labeled set measures how often the
faithfulness judge agrees with a human; `make calibrate` warns when agreement falls below the floor.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
LABELS_PATH = REPO_ROOT / "eval" / "labels.jsonl"

# judge: (question, answer, source_texts) -> 1.0 (faithful) or 0.0
JudgeFn = Callable[[str, str, Sequence[str]], float]


class LabeledExample(BaseModel):
    question: str
    answer: str
    source: str
    faithful: bool


def load_labels(path: Path = LABELS_PATH) -> list[LabeledExample]:
    out: list[LabeledExample] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out.append(LabeledExample(**json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"labels line {lineno} invalid: {exc}") from exc
    if not out:
        raise ValueError(f"no labeled examples in {path}")
    return out


def agreement(labels: Sequence[LabeledExample], judge: JudgeFn) -> float:
    """Fraction of labeled examples where the judge's verdict matches the human label."""
    if not labels:
        return 1.0
    hits = sum(
        1 for ex in labels if (judge(ex.question, ex.answer, [ex.source]) >= 0.5) == ex.faithful
    )
    return hits / len(labels)


def main() -> None:
    from ballast.core.config import ModelRegistry, Settings, load_thresholds
    from ballast.core.cost import CostMeter
    from ballast.core.llm import ClaudeClient
    from ballast.core.trace import MeteredClient, Trace
    from ballast.eval.metrics.faithfulness import faithfulness_score

    settings = Settings()
    registry = ModelRegistry()
    judge_client = MeteredClient(
        ClaudeClient(settings.resolve_api_key()), CostMeter(settings.run_budget_usd), Trace("cal")
    )
    labels = load_labels()
    acc = agreement(
        labels, lambda q, a, s: faithfulness_score(judge_client, q, a, s, registry=registry)
    )
    floor = load_thresholds().get("judge_agreement_min", 0.8)
    print(f"judge agreement with human labels: {acc:.1%} (n={len(labels)})")
    if acc < floor:
        print(f"WARNING: judge agreement {acc:.1%} below floor {floor:.1%}; recalibrate the judge")


if __name__ == "__main__":
    main()
