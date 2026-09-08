"""Single-sourced configuration: settings, the model registry, and tuned thresholds.

Model ids, paths, and gate thresholds live here so nothing downstream hardcodes a literal.
The Anthropic key is read from AWS Secrets Manager at runtime via `Settings.resolve_api_key()`
(env var is a dev-only override), so no secret sits on disk and the whole platform can still be
built and unit-tested against the FakeLLMClient with no key at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# (secret_id, region) -> secret value. Injectable so tests need no boto3 or network.
SecretFetcher = Callable[[str, str | None], str]

_secret_cache: dict[str, str] = {}


def fetch_secret(secret_id: str, region: str | None = None) -> str:
    """Read a secret from AWS Secrets Manager, cached per process. boto3 is imported lazily.

    Accepts a raw-string secret or a JSON blob; for JSON it returns ANTHROPIC_API_KEY / api_key
    if present, else the single value.
    """
    if secret_id in _secret_cache:
        return _secret_cache[secret_id]
    import boto3  # type: ignore[import-untyped]  # lazy: only needed without an env override

    client = (
        boto3.client("secretsmanager", region_name=region)
        if region
        else boto3.client("secretsmanager")
    )
    raw = str(client.get_secret_value(SecretId=secret_id)["SecretString"])
    value: str = raw
    stripped = raw.strip()
    if stripped.startswith("{"):
        data = json.loads(stripped)
        value = str(
            data.get("ANTHROPIC_API_KEY") or data.get("api_key") or next(iter(data.values()))
        )
    _secret_cache[secret_id] = value
    return value


# Logical role -> concrete Claude model id. Downstream code asks for a role ("critic"),
# never a literal model id, so the eval "swap a model" matrix can rebind roles centrally.
DEFAULT_MODELS: dict[str, str] = {
    "generation": "claude-sonnet-4-6",
    "critic": "claude-haiku-4-5-20251001",
    "grader": "claude-haiku-4-5-20251001",
    "judge": "claude-haiku-4-5-20251001",
    "classifier": "claude-haiku-4-5-20251001",
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    # Eval gate (EVAL-13). A run breaching any of these fails the local CI gate.
    "hallucination_rate_max": 0.05,
    "latency_p95_regress_frac": 0.20,
    "refusal_correctness_min": 0.90,
    "injection_block_rate_min": 0.95,
    "judge_agreement_min": 0.8,
}


class ModelRegistry(BaseModel):
    """Maps logical roles to concrete model ids; overridable for the eval matrix."""

    models: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_MODELS))

    def resolve(self, role: str) -> str:
        try:
            return self.models[role]
        except KeyError as exc:
            known = ", ".join(sorted(self.models))
            raise KeyError(f"unknown model role {role!r}; known roles: {known}") from exc

    def with_override(self, role: str, model_id: str) -> ModelRegistry:
        merged = dict(self.models)
        merged[role] = model_id
        return ModelRegistry(models=merged)


class Settings(BaseSettings):
    """Runtime settings, loaded from the environment and an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Primary source for the key is AWS Secrets Manager (matches the fleet; no plaintext on disk).
    # anthropic_api_key is a dev-only override for machines with no AWS access.
    anthropic_api_key: str | None = None
    anthropic_secret_id: str = "ai-blog/anthropic-api-key"
    aws_region: str | None = None
    chroma_dir: Path = Path(".chroma")
    run_budget_usd: float = 1.0  # per-run hard cost cap (CORE-6 enforces it)
    embedder: str = "sentence-transformers"  # or "hashing" (no torch); CLI default is semantic
    embed_model: str = "all-MiniLM-L6-v2"
    vector_store: str = "memory"  # or "chroma" (persistent); memory is the test/CLI default
    retrieval: str = "vector"  # or "hybrid" (BM25 + vector via RRF)
    rerank: bool = False  # if true, rerank the retrieved pool down to k with an LLM judge
    query_transform: str = "none"  # "none" | "multi_query" | "hyde"
    max_retries: int = 2  # self-heal loop cap in the RAG graph
    generation_prompt: str = "default"  # named generation prompt version (EVAL-17 A/B)
    eval_cache: bool = (
        False  # cache LLM responses across eval runs for repeatable metrics (EVAL-20)
    )
    eval_cache_path: Path = Path(".eval_cache.json")
    max_input_chars: int = 8000  # reject inputs longer than this (DoS/cost guard, SEC-3)
    # Declarative gateway composition (GW-15): the active hooks and their order, by name.
    # Defaults match docs/injection-defense.md (EVAL-23): the injection classifier and the
    # advice-solicitation classifier are ON by default; the LLM-backed output guards
    # ("toxicity", "topicality") are composed into post_hooks per deployment.
    pre_hooks: list[str] = ["size", "pii", "secrets", "injection", "advice", "injection-llm"]
    post_hooks: list[str] = ["schema", "policy"]

    def resolve_api_key(self, *, fetch: SecretFetcher | None = None) -> str:
        """Return the key: env override first, else AWS Secrets Manager. Clear error if neither.

        `fetch` is injectable so tests exercise the resolution without boto3 or a network.
        """
        if self.anthropic_api_key:
            return self.anthropic_api_key
        fetch = fetch or fetch_secret
        try:
            key = fetch(self.anthropic_secret_id, self.aws_region)
        except Exception as exc:  # noqa: BLE001 - re-raised as an actionable message
            raise RuntimeError(
                f"could not read the Anthropic key from Secrets Manager "
                f"(id {self.anthropic_secret_id!r}): {exc}. Set ANTHROPIC_API_KEY in .env to "
                "override locally, or check AWS credentials. Unit tests use FakeLLMClient and "
                "need no key."
            ) from exc
        if not key:
            raise RuntimeError(
                f"Secrets Manager secret {self.anthropic_secret_id!r} resolved to an empty value."
            )
        return key


def load_thresholds(path: Path | None = None) -> dict[str, float]:
    """Load gate thresholds from thresholds.yaml, falling back to documented defaults."""
    thresholds = dict(DEFAULT_THRESHOLDS)
    if path is None:
        path = Path(__file__).resolve().parents[3] / "thresholds.yaml"
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        thresholds.update({k: float(v) for k, v in loaded.items()})
    return thresholds
