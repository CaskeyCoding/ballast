"""GW-15: the gateway hook stack is composed from config by name and order."""

from __future__ import annotations

import pytest

from ballast.core.config import ModelRegistry, Settings
from ballast.core.testing import FakeLLMClient
from ballast.gateway.compose import HookContext, compose_post, compose_pre


def _ctx() -> HookContext:
    return HookContext(FakeLLMClient([]), ModelRegistry(), Settings(_env_file=None))  # type: ignore[call-arg]


def test_pre_hooks_composed_in_order() -> None:
    pre = compose_pre(["injection", "pii", "size"], _ctx())
    assert [h.name for h in pre] == ["injection", "pii", "size-limit"]


def test_post_hooks_composed() -> None:
    post = compose_post(["policy", "schema"], _ctx())
    assert [h.name for h in post] == ["policy", "schema"]


def test_optional_llm_hooks_can_be_included() -> None:
    pre = compose_pre(["injection-llm"], _ctx())
    post = compose_post(["toxicity", "topicality"], _ctx())
    assert pre[0].name == "injection-llm"
    assert [h.name for h in post] == ["toxicity", "topicality"]


def test_default_stack_wires_both_input_classifiers() -> None:
    # EVAL-23: docs/injection-defense.md promises the classifier layers by default.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    pre = compose_pre(settings.pre_hooks, _ctx())
    names = [h.name for h in pre]
    assert "injection-llm" in names
    assert "advice-solicitation" in names
    assert names.index("injection") < names.index("advice-solicitation")


def test_unknown_hook_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown pre-hook"):
        compose_pre(["nope"], _ctx())
    with pytest.raises(ValueError, match="unknown post-hook"):
        compose_post(["nope"], _ctx())
