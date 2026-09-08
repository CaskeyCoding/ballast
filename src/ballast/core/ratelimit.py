"""In-process rate limiting: a concurrency cap and a per-minute sliding window.

A batch eval over 100+ questions would trip provider rate limits without this. The clock and sleep
are injectable so the per-minute throttle is testable without real waiting.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class RateLimiter:
    def __init__(
        self,
        *,
        max_concurrent: int = 8,
        per_minute: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sem = threading.BoundedSemaphore(max_concurrent)
        self._per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        if self._per_minute is None:
            return
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= 60.0:
                self._calls.popleft()
            if len(self._calls) >= self._per_minute:
                wait = 60.0 - (now - self._calls[0])
                if wait > 0:
                    self._sleep(wait)
                self._calls.popleft()
            self._calls.append(self._clock())

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Acquire a concurrency slot and respect the per-minute budget for the duration."""
        self._sem.acquire()
        try:
            self._throttle()
            yield
        finally:
            self._sem.release()
