"""EVAL-20: a persisted response cache makes a second run reuse identical responses."""

from __future__ import annotations

from pathlib import Path

from ballast.core.cache import CachingClient, ResponseCache
from ballast.core.testing import FakeLLMClient


def test_cache_persists_and_reuses_across_runs(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    msgs = [{"role": "user", "content": "q"}]

    # first "run": one scripted response, populate and save the cache
    run1 = CachingClient(FakeLLMClient(["the only answer"]), ResponseCache())
    first = run1.complete(msgs, model="m").text
    run1._cache.save(path)  # type: ignore[attr-defined]

    # second "run": the base is exhausted (would raise), but the cache supplies the answer
    cache2 = ResponseCache.load(path)
    run2 = CachingClient(FakeLLMClient([]), cache2)
    second = run2.complete(msgs, model="m").text

    assert first == second == "the only answer"
    assert run2.hits == 1 and run2.misses == 0  # served entirely from the persisted cache


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    cache = ResponseCache()
    CachingClient(FakeLLMClient(["x"]), cache).complete(
        [{"role": "user", "content": "q"}], model="m"
    )
    cache.save(path)
    assert ResponseCache.load(path)._store  # non-empty after reload
