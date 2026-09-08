#!/usr/bin/env python3
"""Offline dependency vulnerability audit (a local, network-free pip-audit stand-in).

Checks installed package versions against a curated advisory denylist and fails the build if any
installed dependency falls in a known-vulnerable range. Wired into scripts/local_ci.py so a
vulnerable pin surfaces locally without a network call. For the full online database, run pip-audit.
"""

from __future__ import annotations

import importlib.metadata as md

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

# (package, vulnerable-version specifier, advisory id). Extend as advisories land.
ADVISORIES: list[tuple[str, str, str]] = [
    ("pyyaml", "<5.4", "CVE-2020-14343 (arbitrary code via full_load)"),
    ("requests", "<2.31.0", "CVE-2023-32681 (proxy cred leak)"),
    ("jinja2", "<3.1.3", "CVE-2024-22195 (xss in xmlattr)"),
    ("urllib3", "<1.26.18", "CVE-2023-45803 (request body on redirect)"),
    ("certifi", "<2023.7.22", "CVE-2023-37920 (removed e-Tugra root)"),
]


def installed_versions() -> dict[str, str]:
    return {dist.metadata["Name"].lower(): dist.version for dist in md.distributions()}


def audit(installed: dict[str, str]) -> list[str]:
    findings: list[str] = []
    for package, spec, advisory in ADVISORIES:
        version = installed.get(package.lower())
        if version is None:
            continue
        try:
            if Version(version) in SpecifierSet(spec):
                findings.append(f"{package} {version} is vulnerable: {advisory}")
        except InvalidVersion:
            continue
    return findings


def main() -> int:
    findings = audit(installed_versions())
    if findings:
        print("DEPENDENCY AUDIT FAILED:")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("dependency audit clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
