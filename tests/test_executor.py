from pathlib import Path

from betterterminal.executor import is_interactive, run_external, run_interactive


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


def test_is_interactive_basename():
    assert is_interactive(["claude"]) is True
    assert is_interactive(["/usr/local/bin/vim"]) is True
    assert is_interactive(["python3"]) is True


def test_is_interactive_false_for_regular():
    assert is_interactive(["ls"]) is False
    assert is_interactive(["git", "status"]) is False
    assert is_interactive([]) is False


def test_is_interactive_env_extension(monkeypatch):
    monkeypatch.setenv("BETTERTERMINAL_INTERACTIVE", "mytool, another")
    assert is_interactive(["mytool"]) is True
    assert is_interactive(["/opt/bin/another"]) is True
    assert is_interactive(["ls"]) is False


def test_run_interactive_returncodes(tmp_path):
    # `true`/`false` never read stdin, so inherited stdio is safe under pytest.
    assert run_interactive(["true"], tmp_path).returncode == 0
    assert run_interactive(["false"], tmp_path).returncode == 1


def test_run_interactive_not_found(tmp_path):
    r = run_interactive(["this-command-does-not-exist-xyz"], tmp_path)
    assert r.returncode == 127
    assert "not found" in r.error
