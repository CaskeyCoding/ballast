"""SEC-5: redaction masks PII/secrets, and logs + traces apply it."""

from __future__ import annotations

import io
import json

from ballast.core.logging import get_logger
from ballast.core.redact import redact
from ballast.core.trace import Trace

_CARD = "4242 4242 4242 4242"  # Luhn-valid test card
_KEY = "sk-" + "ant-" + "A" * 30


def test_redact_masks_pii_and_secrets() -> None:
    out = redact(f"card {_CARD} ssn 123-45-6789 mail a@b.com key {_KEY}")
    assert _CARD not in out
    assert "123-45-6789" not in out
    assert "a@b.com" not in out
    assert "sk-ant" not in out
    assert "[REDACTED_CARD]" in out and "[REDACTED_SECRET]" in out


def test_non_card_digits_not_masked() -> None:
    # a non-Luhn 16-digit run is not a card
    assert "[REDACTED_CARD]" not in redact("order 1234567812345670000")


def test_logger_redacts_by_default() -> None:
    stream = io.StringIO()
    get_logger("r", stream=stream).info(f"charging {_CARD} now")
    assert _CARD not in stream.getvalue()
    assert "[REDACTED_CARD]" in stream.getvalue()


def test_trace_serializer_redacts_free_text() -> None:
    trace = Trace(run_id="t")
    trace.record_node("input", f"user pasted {_CARD}")
    trace.record_decision("guardrail", "blocked", f"saw {_KEY}")
    blob = json.dumps(trace.to_dict())
    assert _CARD not in blob
    assert "sk-ant" not in blob
    assert "[REDACTED_CARD]" in blob and "[REDACTED_SECRET]" in blob
