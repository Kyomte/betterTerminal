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


def run_external(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> ExecResult:
    """Run a single external command and capture stdout/stderr.

    Notes:
    - No PTY: interactive programs (vim, less, python REPL) won't work properly.
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
