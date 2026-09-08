"""Structured JSON logging with a per-run correlation id and a redaction hook.

Every line is JSON carrying the run id, so a self-heal loop or a guardrail block can be traced back
to its run. The redaction hook is applied to every message before it is written, so SEC-5 can wire
real PII/secret masking in one place rather than trusting every call site.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import IO, Any

from ballast.core.redact import redact as default_redact

Redactor = Callable[[str], str]


class JsonFormatter(logging.Formatter):
    def __init__(self, redact: Redactor) -> None:
        super().__init__()
        self._redact = redact

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "run_id": getattr(record, "run_id", None),
            "logger": record.name,
            "msg": self._redact(record.getMessage()),
        }
        return json.dumps(payload)


def get_logger(
    run_id: str,
    *,
    redact: Redactor | None = None,
    stream: IO[str] | None = None,
    level: int = logging.INFO,
) -> logging.LoggerAdapter[logging.Logger]:
    """Return a logger that emits JSON lines tagged with `run_id`. `stream` is for tests.

    Redaction is on by default (SEC-5): pass an explicit `redact` to override.
    """
    redactor: Redactor = redact or default_redact
    logger = logging.getLogger(f"ballast.run.{run_id}")
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()
    handler: logging.Handler = logging.StreamHandler(stream) if stream else logging.StreamHandler()
    handler.setFormatter(JsonFormatter(redactor))
    logger.addHandler(handler)
    return logging.LoggerAdapter(logger, {"run_id": run_id})
