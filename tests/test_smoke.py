"""Smoke test: the package imports and reports its version."""

import ballast


def test_package_imports() -> None:
    assert ballast.__version__ == "0.0.1"
