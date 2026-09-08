"""Declarative gateway composition (GW-15): build the hook stack from config by name and order.

A deployment lists its pre-hooks and post-hooks by name (in `Settings.pre_hooks` / `post_hooks`).
This registry maps each name to a factory, so the guardrail stack is composed without code. An
unknown name fails loudly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ballast.core.config import ModelRegistry, Settings
from ballast.core.llm import LLMClient
from ballast.gateway.gateway import PostHook, PreHook
from ballast.gateway.input.advice import AdviceSolicitationGuard
from ballast.gateway.input.injection import InjectionGuard
from ballast.gateway.input.injection_llm import LLMInjectionGuard
from ballast.gateway.input.pii import PIIGuard
from ballast.gateway.input.secrets import SecretGuard
from ballast.gateway.limits import SizeGuard
from ballast.gateway.output.schema import SchemaGuard
from ballast.gateway.output.topicality import TopicalityGuard
from ballast.gateway.output.toxicity import ToxicityGuard
from ballast.gateway.policy import PolicyGuard


@dataclass
class HookContext:
    client: LLMClient
    registry: ModelRegistry
    settings: Settings


PRE_HOOKS: dict[str, Callable[[HookContext], PreHook]] = {
    "size": lambda ctx: SizeGuard(ctx.settings.max_input_chars),
    "pii": lambda ctx: PIIGuard(),
    "secrets": lambda ctx: SecretGuard(),
    "injection": lambda ctx: InjectionGuard(),
    "injection-llm": lambda ctx: LLMInjectionGuard(ctx.client, ctx.registry),
    "advice": lambda ctx: AdviceSolicitationGuard(ctx.client, ctx.registry),
}

POST_HOOKS: dict[str, Callable[[HookContext], PostHook]] = {
    "schema": lambda ctx: SchemaGuard(),
    "policy": lambda ctx: PolicyGuard.from_yaml(),
    "toxicity": lambda ctx: ToxicityGuard(ctx.client, ctx.registry),
    "topicality": lambda ctx: TopicalityGuard(ctx.client, ctx.registry),
}


def compose_pre(names: Sequence[str], ctx: HookContext) -> list[PreHook]:
    out: list[PreHook] = []
    for name in names:
        if name not in PRE_HOOKS:
            raise ValueError(f"unknown pre-hook {name!r}; known: {', '.join(sorted(PRE_HOOKS))}")
        out.append(PRE_HOOKS[name](ctx))
    return out


def compose_post(names: Sequence[str], ctx: HookContext) -> list[PostHook]:
    out: list[PostHook] = []
    for name in names:
        if name not in POST_HOOKS:
            raise ValueError(f"unknown post-hook {name!r}; known: {', '.join(sorted(POST_HOOKS))}")
        out.append(POST_HOOKS[name](ctx))
    return out
