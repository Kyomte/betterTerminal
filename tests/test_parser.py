from clamshell.parser import ParseError, current_token, tokenize
import pytest


def test_tokenize_simple():
    assert tokenize("ls -la") == ["ls", "-la"]


def test_tokenize_quoted():
    assert tokenize('echo "hello world"') == ["echo", "hello world"]


def test_tokenize_escaped():
    assert tokenize(r'echo hi\ there') == ["echo", "hi there"]


def test_tokenize_unclosed_quote_raises():
    with pytest.raises(ParseError):
        tokenize('echo "unclosed')


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize("   ") == []


def test_current_token_middle_of_word():
    line = "git stat"
    token, start = current_token(line, len(line))
    assert token == "stat"
    assert start == 4


def test_current_token_after_space():
    line = "git "
    token, start = current_token(line, len(line))
    assert token == ""
    assert start == 4


def test_current_token_within_word():
    line = "git status"
    token, start = current_token(line, 6)  # cursor inside "status"
    assert token == "status"
    assert start == 4
