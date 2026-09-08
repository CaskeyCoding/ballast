"""CORE-2: settings load, the model registry resolves roles, thresholds load."""

from __future__ import annotations

from pathlib import Path

import pytest

from ballast.core.config import (
    DEFAULT_MODELS,
    ModelRegistry,
    Settings,
    load_thresholds,
)


def test_env_override_wins_without_calling_secrets_manager() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="sk-dev-override")  # type: ignore[call-arg]

    def _fail(_id: str, _region: str | None) -> str:
        raise AssertionError("Secrets Manager must not be called when the env override is set")

    assert settings.resolve_api_key(fetch=_fail) == "sk-dev-override"


def test_resolves_from_secrets_manager_when_no_override() -> None:
    settings = Settings(_env_file=None, anthropic_api_key=None)  # type: ignore[call-arg]
    captured: dict[str, str | None] = {}

    def _fetch(secret_id: str, region: str | None) -> str:
        captured["id"] = secret_id
        return "sk-from-secrets-manager"

    assert settings.resolve_api_key(fetch=_fetch) == "sk-from-secrets-manager"
    assert captured["id"] == "ai-blog/anthropic-api-key"


def test_secrets_failure_raises_actionable_error() -> None:
    settings = Settings(_env_file=None, anthropic_api_key=None)  # type: ignore[call-arg]

    def _boom(_id: str, _region: str | None) -> str:
        raise RuntimeError("no aws creds")

    with pytest.raises(RuntimeError, match="Secrets Manager"):
        settings.resolve_api_key(fetch=_boom)


def test_registry_resolves_known_roles() -> None:
    registry = ModelRegistry()
    assert registry.resolve("generation") == DEFAULT_MODELS["generation"]
    assert registry.resolve("critic") == DEFAULT_MODELS["critic"]


def test_registry_unknown_role_raises() -> None:
    with pytest.raises(KeyError, match="unknown model role"):
        ModelRegistry().resolve("nope")


def test_registry_override_is_isolated() -> None:
    base = ModelRegistry()
    overridden = base.with_override("generation", "claude-haiku-4-5-20251001")
    assert overridden.resolve("generation") == "claude-haiku-4-5-20251001"
    # the override must not mutate the original registry
    assert base.resolve("generation") == DEFAULT_MODELS["generation"]


def test_thresholds_override_defaults(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.yaml"
    path.write_text("hallucination_rate_max: 0.02\n", encoding="utf-8")
    thresholds = load_thresholds(path)
    assert thresholds["hallucination_rate_max"] == 0.02
    # untouched keys keep their defaults
    assert thresholds["refusal_correctness_min"] == 0.90
