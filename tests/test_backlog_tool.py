import importlib.util
import shutil
from pathlib import Path

TOOL_PATH = Path(__file__).parents[1] / "specs" / "_shared" / "tooling" / "backlog.py"


def _load_backlog(path: Path = TOOL_PATH):
    spec = importlib.util.spec_from_file_location("ballast_backlog_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_path_ballast_is_repository_root() -> None:
    backlog = _load_backlog()
    expected = Path(backlog.__file__).resolve().parents[3]
    assert Path(backlog.repo_path("ballast")) == expected


def test_repo_path_specs_is_repository_specs_directory() -> None:
    backlog = _load_backlog()
    expected = Path(backlog.__file__).resolve().parents[3] / "specs"
    assert Path(backlog.repo_path("specs")) == expected


def test_repo_path_unknown_stays_empty() -> None:
    backlog = _load_backlog()
    assert backlog.repo_path("not-a-repo") == ""


def test_repo_paths_are_portable_in_temporary_repository_layout(tmp_path: Path) -> None:
    tool_path = tmp_path / "specs" / "_shared" / "tooling" / "backlog.py"
    tool_path.parent.mkdir(parents=True)
    shutil.copyfile(TOOL_PATH, tool_path)

    backlog = _load_backlog(tool_path)

    assert Path(backlog.repo_path("ballast")) == tmp_path
    assert Path(backlog.repo_path("specs")) == tmp_path / "specs"
