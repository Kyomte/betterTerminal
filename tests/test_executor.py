from pathlib import Path

from betterterminal.executor import run_external


def test_run_echo(tmp_path):
    r = run_external(["echo", "hello"], tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "hello"


def test_run_unknown_command(tmp_path):
    r = run_external(["this-command-does-not-exist-xyz"], tmp_path)
    assert r.returncode == 127
    assert "not found" in r.stderr


def test_run_in_cwd(tmp_path):
    (tmp_path / "marker.txt").touch()
    r = run_external(["ls"], tmp_path)
    assert "marker.txt" in r.stdout


def test_run_nonzero_exit(tmp_path):
    # `false` exits 1
    r = run_external(["false"], tmp_path)
    assert r.returncode == 1
