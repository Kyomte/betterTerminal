from pathlib import Path

from betterterminal.builtins import BuiltinResult, run_builtin
from betterterminal.frecency import FrecencyStore


class FakeState:
    def __init__(self, cwd: Path, db_path: Path):
        self.cwd = cwd
        self.frecency = FrecencyStore(db_path=db_path)


def test_cd_changes_cwd(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    state = FakeState(tmp_path, tmp_path / "f.db")
    r = run_builtin(state, ["cd", "sub"])
    assert r.new_cwd == sub.resolve()
    assert not r.error


def test_cd_missing_directory(tmp_path):
    state = FakeState(tmp_path, tmp_path / "f.db")
    r = run_builtin(state, ["cd", "does-not-exist"])
    assert r.returncode == 1
    assert "no such" in r.error


def test_pwd(tmp_path):
    state = FakeState(tmp_path, tmp_path / "f.db")
    r = run_builtin(state, ["pwd"])
    assert r.output.strip() == str(tmp_path)


def test_exit_flag():
    state = FakeState(Path.cwd(), Path.cwd() / "throwaway.db")
    try:
        r = run_builtin(state, ["exit"])
        assert r.exit is True
    finally:
        (Path.cwd() / "throwaway.db").unlink(missing_ok=True)


def test_j_jumps_to_match(tmp_path):
    target = tmp_path / "alpha-special"
    target.mkdir()
    state = FakeState(tmp_path, tmp_path / "f.db")
    state.frecency.record(target)
    r = run_builtin(state, ["j", "alpha"])
    assert r.new_cwd == target.resolve()


def test_j_no_match(tmp_path):
    state = FakeState(tmp_path, tmp_path / "f.db")
    r = run_builtin(state, ["j", "nothing-matches"])
    assert r.returncode == 1
    assert "no match" in r.error


def test_help_lists_builtins():
    state = FakeState(Path.cwd(), Path.cwd() / "throwaway2.db")
    try:
        r = run_builtin(state, ["help"])
        assert "cd" in r.output
        assert "j" in r.output
        assert "exit" in r.output
    finally:
        (Path.cwd() / "throwaway2.db").unlink(missing_ok=True)
