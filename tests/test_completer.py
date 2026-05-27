from pathlib import Path

from clamshell.completer import suggest
from clamshell.completions import db


def test_load_known_tool():
    git = db.load("git")
    assert git is not None
    assert "status" in git.subcommands
    assert "commit" in git.subcommands


def test_load_unknown_tool():
    assert db.load("definitely-not-a-real-tool-xyz") is None


def test_known_tools_includes_git():
    tools = db.known_tools()
    assert "git" in tools
    assert "npm" in tools


def test_suggest_command_prefix(tmp_path):
    suggestions = suggest("gi", 2, tmp_path)
    names = {s.display for s in suggestions}
    assert "git" in names


def test_suggest_git_subcommands(tmp_path):
    line = "git "
    suggestions = suggest(line, len(line), tmp_path)
    names = {s.display for s in suggestions}
    # All git subcommands present.
    assert {"status", "commit", "add", "push"}.issubset(names)


def test_suggest_git_subcommand_filter(tmp_path):
    line = "git st"
    suggestions = suggest(line, len(line), tmp_path)
    names = {s.display for s in suggestions}
    assert "status" in names
    assert "stash" in names
    assert "commit" not in names


def test_suggest_path_completion(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "albatross").mkdir()
    (tmp_path / "zeta").mkdir()
    line = "ls al"
    suggestions = suggest(line, len(line), tmp_path)
    names = {s.display for s in suggestions}
    assert "alpha/" in names
    assert "albatross/" in names
    assert "zeta/" not in names


def test_suggest_builtin_completion(tmp_path):
    suggestions = suggest("h", 1, tmp_path)
    names = {s.display for s in suggestions}
    assert "help" in names


def test_suggest_j_builtin(tmp_path):
    suggestions = suggest("", 0, tmp_path)
    names = {s.display for s in suggestions}
    assert "j" in names
    assert "cd" in names
    assert "exit" in names
