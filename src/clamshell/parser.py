"""Tokenize a command line into argv."""

from __future__ import annotations

import shlex


class ParseError(ValueError):
    """Raised when the input cannot be tokenized (e.g. unclosed quote)."""


def tokenize(line: str) -> list[str]:
    """Split a command line into argv tokens using POSIX rules.

    Raises ParseError if the line is malformed (e.g. unclosed quotes).
    """
    try:
        return shlex.split(line, posix=True)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def current_token(line: str, cursor: int) -> tuple[str, int]:
    """Return (token, start_index) for the token under the cursor.

    Used by the completer to know what prefix to complete. Whitespace-separated;
    does not handle quoted strings (acceptable for completion UX).
    """
    if cursor > len(line):
        cursor = len(line)
    start = cursor
    while start > 0 and not line[start - 1].isspace():
        start -= 1
    end = cursor
    while end < len(line) and not line[end].isspace():
        end += 1
    return line[start:end], start


def split_words(line: str) -> list[str]:
    """Loose whitespace split — used to determine command vs argument position.

    Unlike tokenize(), this does not raise on unclosed quotes — it just splits.
    """
    return line.split()
