"""Parse and run command lines containing pipes and redirects.

This sits one layer above `executor.run_external`: it splits a line into a
sequence of commands joined by `|`, peels off file redirections (`>`, `>>`,
`<`) from each command, then runs the whole pipeline as a single
`subprocess` chain so the stages stream into one another the way a real shell
would.

Quoting is honoured — `echo "a | b"` is a single command with a literal pipe,
not a two-stage pipeline — because tokenizing uses `shlex` with
`punctuation_chars`, which only treats *unquoted* operator characters as
operators.

Expansion (env vars + globs) is applied to the plain argument tokens of each
stage via `parser.expand`, after operator splitting, so `cat $FILE > out` and
`ls *.py | wc -l` both work.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from betterterminal.executor import ExecResult
from betterterminal.parser import ParseError, expand


# Operator characters shlex should emit as standalone tokens. `>>` is produced
# by shlex automatically when two `>` are adjacent (punctuation runs coalesce).
_OPERATORS = "|<>"


@dataclass
class Redirects:
    stdin: str | None = None       # file path for `<`
    stdout: str | None = None      # file path for `>` / `>>`
    append: bool = False           # True when stdout came from `>>`


@dataclass
class Command:
    argv: list[str]
    redirects: Redirects = field(default_factory=Redirects)


@dataclass
class Pipeline:
    commands: list[Command]


def has_operators(line: str) -> bool:
    """Cheap check: does the line contain an *unquoted* pipe/redirect operator?

    Used by the app to decide whether to take the pipeline path at all. Falls
    back to True on a tokenize error so the real parser can report it.
    """
    try:
        tokens = _lex(line)
    except ParseError:
        return True
    return any(tok in {"|", "<", ">", ">>"} for tok in tokens)


def _lex(line: str) -> list[str]:
    """Tokenize while keeping unquoted operators as their own tokens."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=_OPERATORS)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def parse(line: str) -> Pipeline:
    """Parse a line into a Pipeline of Commands with their redirects.

    Raises ParseError on malformed input (unclosed quote, missing redirect
    target, empty pipeline stage, etc).
    """
    tokens = _lex(line)

    stages: list[list[str]] = [[]]
    for tok in tokens:
        if tok == "|":
            stages.append([])
        else:
            stages[-1].append(tok)

    commands: list[Command] = []
    for stage in stages:
        commands.append(_parse_stage(stage))
    return Pipeline(commands=commands)


def _parse_stage(tokens: list[str]) -> Command:
    argv: list[str] = []
    redirects = Redirects()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in (">", ">>", "<"):
            if i + 1 >= len(tokens):
                raise ParseError(f"expected filename after '{tok}'")
            target = tokens[i + 1]
            if target in (">", ">>", "<", "|"):
                raise ParseError(f"expected filename after '{tok}'")
            if tok == "<":
                redirects.stdin = target
            else:
                redirects.stdout = target
                redirects.append = tok == ">>"
            i += 2
            continue
        argv.append(tok)
        i += 1

    if not argv:
        raise ParseError("empty command in pipeline")
    return Command(argv=argv, redirects=redirects)


def run_pipeline(
    pipeline: Pipeline, cwd: Path, env: dict[str, str] | None = None
) -> ExecResult:
    """Run a parsed pipeline, wiring stdout->stdin between stages.

    Each stage's plain argv tokens are expanded (vars + globs) just before
    launch. Only the final stage's stdout is captured for display; stderr from
    every stage is merged. File redirects on the first/last stage are honoured.
    """
    environ = env or os.environ.copy()
    commands = pipeline.commands
    procs: list[subprocess.Popen] = []
    open_files: list = []

    try:
        prev_stdout = None  # read end of the previous pipe
        for idx, command in enumerate(commands):
            is_first = idx == 0
            is_last = idx == len(commands) - 1
            argv = expand(command.argv, cwd, env)
            if not argv:
                raise ParseError("empty command in pipeline")

            # --- stdin ---
            stdin = None
            if command.redirects.stdin is not None:
                try:
                    fh = open(_resolve(command.redirects.stdin, cwd), "rb")
                except FileNotFoundError:
                    return ExecResult(
                        stdout="",
                        stderr=f"betterterminal: {command.redirects.stdin}: "
                        "no such file\n",
                        returncode=1,
                    )
                open_files.append(fh)
                stdin = fh
            elif not is_first:
                stdin = prev_stdout

            # --- stdout ---
            stdout = None
            out_file = None
            if command.redirects.stdout is not None:
                mode = "ab" if command.redirects.append else "wb"
                out_file = open(_resolve(command.redirects.stdout, cwd), mode)
                open_files.append(out_file)
                stdout = out_file
            elif not is_last:
                stdout = subprocess.PIPE
            else:
                stdout = subprocess.PIPE  # capture final stage for display

            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=str(cwd),
                    env=environ,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=subprocess.PIPE,
                    text=False,
                )
            except FileNotFoundError:
                _cleanup(procs, open_files)
                return ExecResult(
                    stdout="",
                    stderr=f"betterterminal: command not found: {argv[0]}\n",
                    returncode=127,
                )
            except PermissionError as exc:
                _cleanup(procs, open_files)
                return ExecResult(stdout="", stderr=f"betterterminal: {exc}\n", returncode=126)

            # The previous stage owns the write end of the pipe feeding us; close
            # our copy so it sees EOF when that stage finishes.
            if prev_stdout is not None:
                prev_stdout.close()
            prev_stdout = proc.stdout
            procs.append(proc)

        # Collect output. Only the last process' stdout matters for display.
        # `communicate()` reads and closes the last stage's stdout *and* stderr.
        last = procs[-1]
        out_bytes, last_err = last.communicate()
        # Drain stderr from the upstream stages and wait for them.
        stderr_parts: list[str] = []
        for proc in procs[:-1]:
            proc.wait()
            if proc.stderr is not None:
                err = proc.stderr.read()
                if err:
                    stderr_parts.append(err.decode(errors="replace"))
        if last_err:
            stderr_parts.append(last_err.decode(errors="replace"))

        stdout_text = (out_bytes or b"").decode(errors="replace")
        return ExecResult(
            stdout=stdout_text,
            stderr="".join(stderr_parts),
            returncode=last.returncode or 0,
        )
    finally:
        for fh in open_files:
            try:
                fh.close()
            except OSError:
                pass


def _resolve(path: str, cwd: Path) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = cwd / p
    return str(p)


def _cleanup(procs: list[subprocess.Popen], open_files: list) -> None:
    for proc in procs:
        try:
            proc.kill()
        except OSError:
            pass
    for fh in open_files:
        try:
            fh.close()
        except OSError:
            pass
