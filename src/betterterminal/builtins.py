"""Shell built-ins. They run in-process so they can mutate shell state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from betterterminal.frecency import FrecencyStore


@dataclass
class BuiltinResult:
    output: str = ""
    error: str = ""
    returncode: int = 0
    exit: bool = False
    new_cwd: Path | None = None


class ShellState(Protocol):
    cwd: Path
    prev_cwd: Path | None
    frecency: FrecencyStore


BuiltinFn = Callable[[ShellState, list[str]], BuiltinResult]


def builtin_exit(state: ShellState, args: list[str]) -> BuiltinResult:
    return BuiltinResult(exit=True)


def builtin_cd(state: ShellState, args: list[str]) -> BuiltinResult:
    if len(args) > 1:
        return BuiltinResult(error="cd: too many arguments\n", returncode=1)
    if args and args[0] == "-":
        prev = getattr(state, "prev_cwd", None)
        if prev is None:
            return BuiltinResult(error="cd: no previous directory\n", returncode=1)
        if not prev.is_dir():
            return BuiltinResult(error=f"cd: no such directory: {prev}\n", returncode=1)
        state.frecency.record(prev)
        # Like POSIX shells, `cd -` echoes the directory it lands in.
        return BuiltinResult(new_cwd=prev, output=str(prev) + "\n")
    target = args[0] if args else str(Path.home())
    expanded = Path(target).expanduser()
    if not expanded.is_absolute():
        expanded = state.cwd / expanded
    try:
        resolved = expanded.resolve(strict=True)
    except FileNotFoundError:
        return BuiltinResult(error=f"cd: no such directory: {target}\n", returncode=1)
    if not resolved.is_dir():
        return BuiltinResult(error=f"cd: not a directory: {target}\n", returncode=1)
    state.frecency.record(resolved)
    return BuiltinResult(new_cwd=resolved)


def builtin_pwd(state: ShellState, args: list[str]) -> BuiltinResult:
    return BuiltinResult(output=str(state.cwd) + "\n")


def builtin_j(state: ShellState, args: list[str]) -> BuiltinResult:
    """Fuzzy jump — `j <query>` jumps to best frecency match, `j` lists top 10."""
    needle = " ".join(args)
    matches = state.frecency.query(needle, limit=10)
    if not needle:
        if not matches:
            return BuiltinResult(output="(no directories tracked yet)\n")
        lines = [f"  {score:>8.1f}  {path}" for path, score in matches]
        return BuiltinResult(output="\n".join(lines) + "\n")
    if not matches:
        return BuiltinResult(error=f"j: no match for {needle!r}\n", returncode=1)
    target = matches[0][0]
    state.frecency.record(target)
    return BuiltinResult(new_cwd=target, output=f"-> {target}\n")


def builtin_help(state: ShellState, args: list[str]) -> BuiltinResult:
    text = (
        "betterterminal built-ins:\n"
        "  cd [dir]        change directory (default: $HOME; `cd -` toggles previous)\n"
        "  pwd             print working directory\n"
        "  j [query]       fuzzy-jump to a tracked directory (no query: list top)\n"
        "  exit            quit betterterminal\n"
        "  help            show this message\n"
        "\n"
        "Tab completes commands, subcommands, and paths.\n"
    )
    return BuiltinResult(output=text)


BUILTINS: dict[str, BuiltinFn] = {
    "exit": builtin_exit,
    "quit": builtin_exit,
    "cd": builtin_cd,
    "pwd": builtin_pwd,
    "j": builtin_j,
    "help": builtin_help,
}


def is_builtin(name: str) -> bool:
    return name in BUILTINS


def run_builtin(state: ShellState, argv: list[str]) -> BuiltinResult:
    fn = BUILTINS[argv[0]]
    return fn(state, argv[1:])
