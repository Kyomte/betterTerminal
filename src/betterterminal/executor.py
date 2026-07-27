"""Run external commands."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass
class InteractiveResult:
    returncode: int
    error: str = ""  # set only on launch failure (not-found / permission)


# Programs that take over the terminal (full-screen TUIs, REPLs, pagers). These
# can't run captured — they need a real TTY, so the app runs them via
# App.suspend() + run_interactive() instead of run_external().
_INTERACTIVE_PROGRAMS: frozenset[str] = frozenset(
    {
        "claude",
        "vim", "vi", "nvim", "nano", "emacs",
        "less", "more", "man",
        "top", "htop",
        "ssh",
        "python", "python3", "ipython",
        "node", "irb", "psql", "sqlite3",
    }
)


def _interactive_names() -> set[str]:
    """Allowlist plus any user additions from $BETTERTERMINAL_INTERACTIVE."""
    names = set(_INTERACTIVE_PROGRAMS)
    for token in os.environ.get("BETTERTERMINAL_INTERACTIVE", "").split(","):
        token = token.strip()
        if token:
            names.add(token)
    return names


def is_interactive(argv: list[str]) -> bool:
    """True if argv[0]'s basename is a known interactive program."""
    if not argv:
        return False
    return os.path.basename(argv[0]) in _interactive_names()


def run_external(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> ExecResult:
    """Run a single external command and capture stdout/stderr.

    For interactive programs (vim, less, REPLs, claude) use run_interactive()
    instead — they need a real TTY, which capture mode does not provide.

    Notes:
    - No pipes/redirects in MVP.
    """
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env or os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
        return ExecResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
    except FileNotFoundError:
        return ExecResult(
            stdout="",
            stderr=f"betterterminal: command not found: {argv[0]}\n",
            returncode=127,
        )
    except PermissionError as exc:
        return ExecResult(stdout="", stderr=f"betterterminal: {exc}\n", returncode=126)


def run_interactive(
    argv: list[str], cwd: Path, env: dict[str, str] | None = None
) -> InteractiveResult:
    """Run an interactive program with INHERITED stdio (the real TTY).

    The caller must first drop out of the Textual TUI (App.suspend()), otherwise
    the app and the child fight over the terminal. Because stdio is inherited
    there is no captured stderr, so launch failures (not-found / permission) are
    reported via the returned `error` field for the app to print after resuming.
    """
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env or os.environ.copy(),
            check=False,
        )
        return InteractiveResult(returncode=completed.returncode)
    except FileNotFoundError:
        return InteractiveResult(
            returncode=127,
            error=f"betterterminal: command not found: {argv[0]}\n",
        )
    except PermissionError as exc:
        return InteractiveResult(returncode=126, error=f"betterterminal: {exc}\n")
