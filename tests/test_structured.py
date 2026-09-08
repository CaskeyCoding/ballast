"""CORE-4: complete_structured validates, repairs once, or raises."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from ballast.core.structured import StructuredError, complete_structured
from ballast.core.testing import FakeLLMClient


class Grade(BaseModel):
    grounded: bool
    reason: str


def test_clean_json_validates() -> None:
    fake = FakeLLMClient(['{"grounded": true, "reason": "supported by chunk 2"}'])
    out = complete_structured(fake, [{"role": "user", "content": "grade"}], Grade, model="m")
    assert out.grounded is True
    assert out.reason.startswith("supported")


def test_code_fence_is_stripped() -> None:
    fake = FakeLLMClient(['```json\n{"grounded": false, "reason": "no support"}\n```'])
    out = complete_structured(fake, [{"role": "user", "content": "grade"}], Grade, model="m")
    assert out.grounded is False


def test_malformed_then_repaired() -> None:
    fake = FakeLLMClient(["not json at all", '{"grounded": true, "reason": "fixed on retry"}'])
    out = complete_structured(fake, [{"role": "user", "content": "grade"}], Grade, model="m")
    assert out.reason == "fixed on retry"
    assert len(fake.calls) == 2  # original + one repair


def test_twice_bad_raises() -> None:
    fake = FakeLLMClient(["garbage", "still garbage"])
    with pytest.raises(StructuredError, match="not satisfied after repair"):
        complete_structured(fake, [{"role": "user", "content": "grade"}], Grade, model="m")
