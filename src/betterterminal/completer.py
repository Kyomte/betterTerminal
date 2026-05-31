"""Suggest completions for the current input."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from betterterminal.builtins import BUILTINS
from betterterminal.completions import db, help_parser
from betterterminal.parser import current_token, split_words


@dataclass
class Suggestion:
    text: str             # text to insert
    display: str          # what the popup shows
    description: str = ""

    def __hash__(self) -> int:
        return hash(self.text)


def _executables_on_path() -> list[str]:
    """Collect executable names from $PATH. Cached after first call."""
    global _PATH_CACHE
    if _PATH_CACHE is not None:
        return _PATH_CACHE
    seen: set[str] = set()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isdir(entry):
            continue
        try:
            for name in os.listdir(entry):
                full = os.path.join(entry, name)
                if os.access(full, os.X_OK) and not os.path.isdir(full):
                    seen.add(name)
        except OSError:
            continue
    _PATH_CACHE = sorted(seen)
    return _PATH_CACHE


_PATH_CACHE: list[str] | None = None


def _path_completions(prefix: str, cwd: Path) -> list[Suggestion]:
    """Filesystem path completion (files and directories)."""
    expanded = Path(prefix).expanduser() if prefix else Path()
    if prefix.endswith("/") or prefix == "":
        directory = expanded if prefix else cwd
        partial = ""
    elif expanded.is_absolute() or prefix.startswith("~"):
        directory = expanded.parent if not expanded.is_dir() else expanded
        partial = expanded.name if not expanded.is_dir() else ""
    else:
        candidate = cwd / expanded
        if candidate.is_dir() and prefix.endswith("/"):
            directory = candidate
            partial = ""
        else:
            directory = (cwd / expanded.parent) if expanded.parent != Path() else cwd
            partial = expanded.name

    if not directory.is_dir():
        return []

    # Preserve the user's prefix shape (e.g. ~/foo, ./foo, foo).
    if prefix.startswith("~"):
        # Insert with ~ preserved by computing the user-facing prefix root.
        home = str(Path.home())
        def to_user(p: Path) -> str:
            s = str(p)
            if s.startswith(home):
                return "~" + s[len(home):]
            return s
        prefix_dir = to_user(directory)
    elif Path(prefix).is_absolute():
        prefix_dir = str(directory)
    else:
        # Relative to cwd — show the prefix the user is typing.
        if "/" in prefix:
            prefix_dir = prefix.rsplit("/", 1)[0]
        else:
            prefix_dir = ""

    results: list[Suggestion] = []
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        if name.startswith(".") and not partial.startswith("."):
            continue
        if not name.lower().startswith(partial.lower()):
            continue
        is_dir = entry.is_dir()
        display_name = name + ("/" if is_dir else "")
        if prefix_dir:
            inserted = f"{prefix_dir}/{name}" + ("/" if is_dir else "")
        else:
            inserted = name + ("/" if is_dir else "")
        results.append(
            Suggestion(
                text=inserted,
                display=display_name,
                description="directory" if is_dir else "file",
            )
        )
    return results[:50]


def _command_completions(prefix: str) -> list[Suggestion]:
    """Complete the first word: built-ins + known tools + $PATH executables."""
    out: list[Suggestion] = []
    seen: set[str] = set()

    for name in BUILTINS:
        if name.startswith(prefix):
            out.append(Suggestion(text=name + " ", display=name, description="built-in"))
            seen.add(name)

    for tool in db.known_tools():
        if tool.startswith(prefix) and tool not in seen:
            out.append(Suggestion(text=tool + " ", display=tool, description="tool (betterterminal knows subcommands)"))
            seen.add(tool)

    if prefix:
        for exe in _executables_on_path():
            if exe.startswith(prefix) and exe not in seen:
                out.append(Suggestion(text=exe + " ", display=exe, description="executable"))
                seen.add(exe)
                if len(out) >= 50:
                    break
    return out


def _subcommand_completions(tool: str, prefix: str) -> list[Suggestion]:
    """Complete subcommands for a known tool. Falls back to --help parser."""
    out: list[Suggestion] = []
    comp = db.load(tool)
    seen: set[str] = set()
    if comp is not None:
        for name, desc in sorted(comp.subcommands.items()):
            if name.startswith(prefix):
                out.append(Suggestion(text=name + " ", display=name, description=desc))
                seen.add(name)
    if not out:
        parsed = help_parser.parse(tool)
        if parsed is not None:
            for name, desc in sorted(parsed.subcommands.items()):
                if name.startswith(prefix) and name not in seen:
                    out.append(Suggestion(text=name + " ", display=name, description=desc))
    return out


def suggest(line: str, cursor: int, cwd: Path) -> list[Suggestion]:
    """Top-level suggestion dispatcher.

    - Cursor is at the first token? complete commands.
    - Cursor in a later token, and the command is a known tool? complete subcommands first, fall back to paths.
    - Otherwise complete filesystem paths.
    """
    token, _ = current_token(line, cursor)
    words = split_words(line[:cursor])

    # Determine position: 0 = command, 1+ = argument.
    if not words or (len(words) == 1 and not line[:cursor].endswith(" ")):
        return _command_completions(token)

    command = words[0]

    # Are we completing the immediate-next-word after the command (i.e. a subcommand)?
    is_subcommand_position = (
        len(words) == 1 and line[:cursor].endswith(" ")
    ) or (len(words) == 2 and not line[:cursor].endswith(" "))

    if is_subcommand_position:
        sub_suggestions = _subcommand_completions(command, token)
        if sub_suggestions:
            return sub_suggestions

    return _path_completions(token, cwd)
