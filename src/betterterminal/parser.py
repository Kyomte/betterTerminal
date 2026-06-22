"""Tokenize a command line into argv."""

from __future__ import annotations

import glob as _glob
import os
import re
import shlex
from pathlib import Path


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


# Matches $VAR, ${VAR}. Names follow the POSIX rule: first char a letter or
# underscore, rest alphanumeric or underscore. `$$` (PID) and other special
# parameters are intentionally out of scope for this MVP.
_VAR_RE = re.compile(r"\$(?:\{(\w+)\}|([A-Za-z_]\w*))")


def expand_vars(token: str, env: dict[str, str] | None = None) -> str:
    """Substitute $VAR / ${VAR} references in a single token.

    Unset variables expand to the empty string (POSIX default). A `$` not
    followed by a valid name is left untouched, so paths like `a$b/c` only
    expand the part that looks like a variable.
    """
    environ = os.environ if env is None else env

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return environ.get(name, "")

    return _VAR_RE.sub(_sub, token)


# Unescaped glob metacharacters. We only treat a token as a glob if it has one
# of these; otherwise globbing is skipped entirely (fast path).
_GLOB_META = re.compile(r"(?<!\\)[*?\[]")


def expand_globs(token: str, cwd: Path) -> list[str]:
    """Expand a glob token (``*``, ``?``, ``[...]``) against `cwd`.

    Returns a sorted list of matches. If the pattern matches nothing it is
    returned unchanged as a single-element list — the same no-match behaviour
    as bash without `nullglob`. Relative patterns resolve against `cwd`;
    matches are returned in the same (relative/absolute) shape they were typed.
    """
    if not _GLOB_META.search(token):
        return [token]

    expanded = os.path.expanduser(token)
    if os.path.isabs(expanded):
        matches = _glob.glob(expanded, recursive=False)
    else:
        base = str(cwd)
        full = os.path.join(base, expanded)
        raw = _glob.glob(full, recursive=False)
        # Strip the cwd prefix back off so results stay relative, matching
        # what the user typed.
        prefix = base + os.sep
        matches = [m[len(prefix):] if m.startswith(prefix) else m for m in raw]

    if not matches:
        return [token]
    return sorted(matches)


def expand(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> list[str]:
    """Apply shell expansions to a tokenized argv, in order: vars, then globs.

    Mirrors the standard shell ordering — variable substitution happens before
    pathname (glob) expansion, so e.g. `$DIR/*.py` works.
    """
    out: list[str] = []
    for token in argv:
        substituted = expand_vars(token, env)
        out.extend(expand_globs(substituted, cwd))
    return out


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
