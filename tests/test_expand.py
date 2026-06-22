"""Tests for environment-variable substitution and glob expansion."""

from pathlib import Path

from betterterminal.parser import expand, expand_globs, expand_vars


# ----- $VAR substitution -----

def test_expand_vars_simple():
    env = {"NAME": "world"}
    assert expand_vars("$NAME", env) == "world"


def test_expand_vars_braced():
    env = {"NAME": "world"}
    assert expand_vars("${NAME}", env) == "world"


def test_expand_vars_embedded():
    env = {"DIR": "proj"}
    assert expand_vars("$DIR/src", env) == "proj/src"
    assert expand_vars("${DIR}_backup", env) == "proj_backup"


def test_expand_vars_unset_is_empty():
    assert expand_vars("$DOES_NOT_EXIST", {}) == ""
    assert expand_vars("a${MISSING}b", {}) == "ab"


def test_expand_vars_lone_dollar_untouched():
    # `$` not followed by a valid name stays literal.
    assert expand_vars("price$5", {}) == "price$5"
    assert expand_vars("$", {}) == "$"


def test_expand_vars_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("BT_TEST_VAR", "hello")
    assert expand_vars("$BT_TEST_VAR") == "hello"


# ----- glob expansion -----

def test_expand_globs_star(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    (tmp_path / "c.txt").touch()
    result = expand_globs("*.py", tmp_path)
    assert result == ["a.py", "b.py"]


def test_expand_globs_question_mark(tmp_path):
    (tmp_path / "a1").touch()
    (tmp_path / "a2").touch()
    (tmp_path / "abc").touch()
    result = expand_globs("a?", tmp_path)
    assert sorted(result) == ["a1", "a2"]


def test_expand_globs_charclass(tmp_path):
    (tmp_path / "file1").touch()
    (tmp_path / "file2").touch()
    (tmp_path / "file9").touch()
    result = expand_globs("file[12]", tmp_path)
    assert result == ["file1", "file2"]


def test_expand_globs_no_match_returns_literal(tmp_path):
    # bash default (no nullglob): unmatched pattern is passed through literally.
    assert expand_globs("*.nomatch", tmp_path) == ["*.nomatch"]


def test_expand_globs_non_glob_passthrough(tmp_path):
    assert expand_globs("plainfile", tmp_path) == ["plainfile"]


def test_expand_globs_results_are_relative(tmp_path):
    (tmp_path / "x.py").touch()
    result = expand_globs("*.py", tmp_path)
    assert result == ["x.py"]  # not the absolute path


# ----- combined expand() -----

def test_expand_vars_then_globs(tmp_path, monkeypatch):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "one.py").touch()
    (sub / "two.py").touch()
    monkeypatch.setenv("SRC", "src")
    result = expand(["$SRC/*.py"], tmp_path)
    assert result == ["src/one.py", "src/two.py"]


def test_expand_preserves_plain_tokens(tmp_path):
    assert expand(["ls", "-la"], tmp_path) == ["ls", "-la"]
