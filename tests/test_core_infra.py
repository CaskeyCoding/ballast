"""CORE-8/9/10: JSON logging with run id + redaction, response cache, rate limiter."""

from __future__ import annotations

import io
import json

from ballast.core.cache import CachingClient, ResponseCache
from ballast.core.llm import LLMClient
from ballast.core.logging import get_logger
from ballast.core.ratelimit import RateLimiter
from ballast.core.testing import FakeLLMClient


# --- CORE-8 logging ---
def test_log_line_is_json_with_run_id() -> None:
    stream = io.StringIO()
    log = get_logger("run-123", stream=stream)
    log.info("hello")
    line = json.loads(stream.getvalue().strip())
    assert line["run_id"] == "run-123"
    assert line["msg"] == "hello"


def test_redaction_hook_is_applied() -> None:
    stream = io.StringIO()
    log = get_logger(
        "r", redact=lambda s: s.replace("4111111111111111", "[REDACTED]"), stream=stream
    )
    log.info("card 4111111111111111 seen")
    assert "[REDACTED]" in stream.getvalue()
    assert "4111111111111111" not in stream.getvalue()


# --- CORE-9 cache ---
def test_cache_hit_avoids_second_call() -> None:
    base = FakeLLMClient(["one", "two"])
    client = CachingClient(base, ResponseCache())
    msgs = [{"role": "user", "content": "q"}]
    first = client.complete(msgs, model="m").text
    second = client.complete(msgs, model="m").text
    assert first == second == "one"
    assert client.hits == 1 and client.misses == 1


def test_cache_misses_on_changed_model() -> None:
    base = FakeLLMClient(["a", "b"])
    client = CachingClient(base, ResponseCache())
    msgs = [{"role": "user", "content": "q"}]
    assert client.complete(msgs, model="m1").text == "a"
    assert client.complete(msgs, model="m2").text == "b"
    assert client.misses == 2


def test_disabled_cache_bypasses() -> None:
    base = FakeLLMClient(["a", "b"])
    client = CachingClient(base, ResponseCache(enabled=False))
    msgs = [{"role": "user", "content": "q"}]
    assert client.complete(msgs, model="m").text == "a"
    assert client.complete(msgs, model="m").text == "b"  # not served from cache


def test_caching_client_satisfies_protocol() -> None:
    assert isinstance(CachingClient(FakeLLMClient(["x"]), ResponseCache()), LLMClient)


# --- CORE-10 rate limiter ---
def test_per_minute_throttle_sleeps_when_over_budget() -> None:
    now = [0.0]
    slept: list[float] = []
    limiter = RateLimiter(per_minute=2, clock=lambda: now[0], sleep=lambda s: slept.append(s))
    for _ in range(2):
        with limiter.slot():
            pass
    # third call within the same minute must wait
    with limiter.slot():
        pass
    assert slept and slept[0] > 0


def test_concurrency_cap_never_exceeded() -> None:
    import threading

    limiter = RateLimiter(max_concurrent=2)
    active = 0
    peak = 0
    lock = threading.Lock()
    barrier = threading.Event()

    def worker() -> None:
        nonlocal active, peak
        with limiter.slot():
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    barrier.set()
    for t in threads:
        t.join()
    assert peak <= 2
