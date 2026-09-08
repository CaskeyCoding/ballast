"""SEC-2: the dependency audit flags a known-vulnerable pin and passes a clean set."""

from __future__ import annotations

from scripts.dep_audit import audit


def test_flags_known_vulnerable_version() -> None:
    findings = audit({"requests": "2.30.0"})  # < 2.31.0 is vulnerable per the denylist
    assert findings and "requests" in findings[0]


def test_clean_versions_pass() -> None:
    assert audit({"requests": "2.32.3", "pyyaml": "6.0.1"}) == []


def test_unknown_package_ignored() -> None:
    assert audit({"some-package-we-do-not-track": "0.0.1"}) == []
