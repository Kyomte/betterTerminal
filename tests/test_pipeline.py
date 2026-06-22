"""Tests for pipe and redirect support."""

from pathlib import Path

import pytest

from betterterminal.parser import ParseError
from betterterminal.pipeline import (
    has_operators,
    parse,
    run_pipeline,
)


# ----- operator detection -----

def test_has_operators_detects_pipe():
    assert has_operators("ls | wc -l") is True


def test_has_operators_detects_redirects():
    assert has_operators("echo hi > out.txt") is True
    assert has_operators("cat >> log") is True
    assert has_operators("sort < in.txt") is True


def test_has_operators_false_for_plain():
    assert has_operators("ls -la") is False


def test_has_operators_ignores_quoted_operators():
    # A pipe inside quotes is a literal, not an operator.
    assert has_operators('echo "a | b"') is False
    assert has_operators("echo 'x > y'") is False


# ----- parsing -----

def test_parse_single_command():
    pipe = parse("ls -la")
    assert len(pipe.commands) == 1
    assert pipe.commands[0].argv == ["ls", "-la"]


def test_parse_pipe_chain():
    pipe = parse("ls | grep py | wc -l")
    assert [c.argv for c in pipe.commands] == [["ls"], ["grep", "py"], ["wc", "-l"]]


def test_parse_output_redirect():
    pipe = parse("echo hi > out.txt")
    cmd = pipe.commands[0]
    assert cmd.argv == ["echo", "hi"]
    assert cmd.redirects.stdout == "out.txt"
    assert cmd.redirects.append is False


def test_parse_append_redirect():
    pipe = parse("echo hi >> out.txt")
    cmd = pipe.commands[0]
    assert cmd.redirects.stdout == "out.txt"
    assert cmd.redirects.append is True


def test_parse_input_redirect():
    pipe = parse("sort < in.txt")
    cmd = pipe.commands[0]
    assert cmd.argv == ["sort"]
    assert cmd.redirects.stdin == "in.txt"


def test_parse_missing_redirect_target_raises():
    with pytest.raises(ParseError):
        parse("echo hi >")


def test_parse_empty_stage_raises():
    with pytest.raises(ParseError):
        parse("ls | | wc")


# ----- execution -----

def test_run_simple_pipe(tmp_path):
    # `printf` two lines, count them with wc -l.
    result = run_pipeline(parse("printf 'a\\nb\\n' | wc -l"), tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "2"


def test_run_pipe_filters(tmp_path):
    result = run_pipeline(parse("printf 'apple\\nbanana\\navocado\\n' | grep a"), tmp_path)
    assert "apple" in result.stdout
    assert "avocado" in result.stdout


def test_run_output_redirect_creates_file(tmp_path):
    result = run_pipeline(parse("echo hello > out.txt"), tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "out.txt").read_text().strip() == "hello"


def test_run_append_redirect(tmp_path):
    run_pipeline(parse("echo one > log.txt"), tmp_path)
    run_pipeline(parse("echo two >> log.txt"), tmp_path)
    assert (tmp_path / "log.txt").read_text().splitlines() == ["one", "two"]


def test_run_input_redirect(tmp_path):
    (tmp_path / "data.txt").write_text("zebra\napple\nmango\n")
    result = run_pipeline(parse("sort < data.txt"), tmp_path)
    assert result.stdout.splitlines() == ["apple", "mango", "zebra"]


def test_run_pipe_with_redirect_at_end(tmp_path):
    run_pipeline(parse("printf 'b\\na\\n' | sort > sorted.txt"), tmp_path)
    assert (tmp_path / "sorted.txt").read_text().splitlines() == ["a", "b"]


def test_run_pipeline_command_not_found(tmp_path):
    result = run_pipeline(parse("this-cmd-xyz | wc -l"), tmp_path)
    assert result.returncode == 127
    assert "not found" in result.stderr


def test_run_pipeline_expands_globs(tmp_path):
    (tmp_path / "a.py").touch()
    (tmp_path / "b.py").touch()
    result = run_pipeline(parse("echo *.py | wc -w"), tmp_path)
    assert result.stdout.strip() == "2"


def test_run_pipeline_expands_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("GREETING", "hiya")
    result = run_pipeline(parse("echo $GREETING"), tmp_path)
    assert result.stdout.strip() == "hiya"
