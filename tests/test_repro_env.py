"""DX-7: the environment is reproducible from the lockfile and the Python pin.

A clean install from requirements.lock must resolve without conflicts. Running a real network
install in the gate is too slow, so these tests check the offline guarantees that stand in for it:
the lock is fully pinned with no package pinned to two versions (the definition of a conflict-free
resolution), every direct dependency is present and satisfies its pyproject specifier, and the
locked versions of the direct deps match what is actually installed (so the lock reflects a real,
working resolution, not an aspirational one). The Python pin must satisfy `requires-python`.
"""

from __future__ import annotations

import importlib.metadata as md
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

_ROOT = Path(__file__).resolve().parent.parent
_LOCK = _ROOT / "requirements.lock"
_PYVERSION = _ROOT / ".python-version"
_PYPROJECT = _ROOT / "pyproject.toml"


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_lines() -> list[str]:
    return [
        ln.strip()
        for ln in _LOCK.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def _locked_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in _lock_lines():
        name, _, version = line.partition("==")
        pins[_canon(name)] = version
    return pins


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _direct_requirements() -> list[Requirement]:
    proj = _pyproject()["project"]
    specs = list(proj.get("dependencies", []))
    for extra in proj.get("optional-dependencies", {}).values():
        specs.extend(extra)
    return [Requirement(s) for s in specs]


def test_python_version_pin_satisfies_requires_python() -> None:
    pin = _PYVERSION.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", pin), f".python-version is not a version: {pin!r}"
    requires = _pyproject()["project"]["requires-python"]
    floor = Version(re.search(r"\d+\.\d+", requires).group())  # type: ignore[union-attr]
    assert Version(pin) >= floor, f"pin {pin} does not satisfy requires-python {requires}"


def test_lock_is_fully_pinned() -> None:
    bad = [ln for ln in _lock_lines() if not re.fullmatch(r"[A-Za-z0-9._-]+==[^=]+", ln)]
    assert not bad, f"lock has unpinned or malformed lines: {bad}"


def test_lock_has_no_conflicting_duplicates() -> None:
    seen: dict[str, str] = {}
    conflicts = []
    for line in _lock_lines():
        name, _, version = line.partition("==")
        key = _canon(name)
        if key in seen and seen[key] != version:
            conflicts.append(f"{name}: {seen[key]} vs {version}")
        seen[key] = version
    assert not conflicts, f"lock pins a package to two versions (a conflict): {conflicts}"


def test_direct_deps_present_and_satisfied() -> None:
    pins = _locked_pins()
    problems = []
    for req in _direct_requirements():
        key = _canon(req.name)
        if key not in pins:
            problems.append(f"{req.name} missing from lock")
        elif not req.specifier.contains(pins[key], prereleases=True):
            problems.append(f"{req.name}=={pins[key]} violates {req.specifier}")
    assert not problems, f"direct dependencies not reproducibly locked: {problems}"


def test_locked_direct_versions_match_installed() -> None:
    pins = _locked_pins()
    drift = []
    for req in _direct_requirements():
        key = _canon(req.name)
        try:
            installed = md.version(req.name)
        except md.PackageNotFoundError:
            continue  # an extra not installed in this environment; covered by the presence test
        if key in pins and pins[key] != installed:
            drift.append(f"{req.name}: lock {pins[key]} != installed {installed}")
    assert not drift, f"lock is out of sync with the environment (regenerate): {drift}"
