# betterterminal

A from-scratch interactive shell with smart autocomplete and zoxide-style
directory jumping, built as a full-screen terminal UI on
[Textual](https://textual.textualize.io/).

It is not a drop-in replacement for bash or zsh — it is a focused, hackable
shell that makes the two things you do most often (running commands and moving
between directories) faster, with completion and fuzzy jumping built in.

## Features

- **Smart Tab completion** for commands, subcommands, and filesystem paths.
  Subcommands come from hand-written data for ~30 common tools (`git`, `gh`,
  `docker`, `cargo`, `kubectl`, `npm`, `uv`, and more); unknown tools fall back
  to parsing `tool --help` and caching the result.
- **Fuzzy directory jumping** with `j` — a zoxide-style frecency ranking
  (frequency × recency) so the directories you visit most are one keystroke
  away.
- **`cd -`** to toggle back to your previous directory.
- **Pipes and redirects** — `|`, `>`, `>>`, and `<` run as a real subprocess
  chain.
- **Environment-variable substitution** — `$VAR` and `${VAR}`.
- **Glob expansion** — `*`, `?`, and `[...]` patterns expand against the
  current directory.
- **Interactive programs** (`vim`, `less`, `python`, `ssh`, REPLs, …) run on
  the real terminal: the UI steps aside, runs the program, then resumes.

## Requirements

- Python 3.11+
- A real terminal (the shell is a full-screen TUI)

## Install

From the project root, create a virtual environment and install the package in
editable mode:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

To also install the test dependencies:

```sh
.venv/bin/pip install -e ".[dev]"
```

## Run

```sh
.venv/bin/betterterminal
```

or equivalently:

```sh
.venv/bin/python -m betterterminal
```

This launches the full-screen UI. Type a command and press Enter to run it;
press Tab to complete; press `Escape` to dismiss the completion popup. On an
empty line, `Ctrl-C` exits (`exit` and `quit` work too).

## Usage

### Running commands

Type any command as you normally would:

```
ls -la
git status
echo hello
```

Output is captured and shown in the scrollback above the prompt.

### Built-ins

| Command      | Description                                                       |
| ------------ | ----------------------------------------------------------------- |
| `cd [dir]`   | Change directory (no argument → `$HOME`). `cd -` toggles previous |
| `pwd`        | Print the working directory                                       |
| `j [query]`  | Fuzzy-jump to a tracked directory; no query lists the top entries |
| `help`       | List the built-ins                                                |
| `exit`/`quit`| Quit betterterminal                                               |

Typing a bare directory name with no command auto-`cd`s into it.

### Directory jumping (`j`)

Every `cd` and `j` trains a frecency database stored at
`~/.betterterminal/frecency.db`. After visiting a few directories you can jump
to any of them by a fuzzy fragment of its name:

```
j proj        # jumps to the highest-ranked directory matching "proj"
j             # lists the top tracked directories with their scores
```

Matching is on the directory's basename, so short fragments stay precise.

### Completion

Press Tab to complete the token under the cursor:

- **First word** → command completion (built-ins, known tools, then `$PATH`
  executables).
- **Word after a known command** → subcommand completion (e.g. `git ` + Tab
  lists `status`, `commit`, …).
- **Anywhere else** → filesystem path completion.

If there is one match it is inserted directly; if several share a longer common
prefix, the input is extended to that prefix before the popup opens.

### Pipes and redirects

```
ls | grep .py | wc -l
echo hello > out.txt
cat notes.txt >> log.txt
sort < unsorted.txt
```

`|` chains commands; `>` writes (truncating), `>>` appends, and `<` reads stdin
from a file. Operators inside quotes are treated literally
(`echo "a | b"` prints `a | b`).

### Variables and globs

```
echo $HOME
cd $PROJECT_DIR
ls *.py
cat report?.txt      # ? matches a single character
ls log[0-9].txt      # [...] matches a character class
```

Variables expand to the empty string when unset (POSIX default). Glob patterns
that match nothing are passed through literally (bash default, no `nullglob`).

### Interactive programs

Full-screen programs, pagers, and REPLs (`vim`, `less`, `man`, `python`, `ssh`,
…) are run on the real terminal: betterterminal drops its UI, runs the program
with inherited stdio, then resumes when it exits. You can extend the recognised
list at runtime with the comma-separated `BETTERTERMINAL_INTERACTIVE`
environment variable:

```sh
BETTERTERMINAL_INTERACTIVE="mytui,anotherrepl" .venv/bin/betterterminal
```

## Development

Run the test suite:

```sh
.venv/bin/pytest tests/
```

Run a single file or test:

```sh
.venv/bin/pytest tests/test_completer.py
.venv/bin/pytest tests/test_completer.py::test_suggest_git_subcommands
```

`pytest` is configured with `asyncio_mode = "auto"`, so async tests (which drive
the real Textual app headlessly) run without per-test decorators.

### Project layout

```
src/betterterminal/
  app.py               Textual app — owns shell state, routes each line
  parser.py            tokenize + variable / glob expansion
  pipeline.py          pipe & redirect parsing and execution
  executor.py          run external / interactive commands
  builtins.py          in-process commands (cd, pwd, j, help, exit)
  completer.py         Tab-completion dispatch
  completions/         subcommand data (JSON) + --help fallback parser
  frecency.py          zoxide-style directory ranking (SQLite)
```

## Adding tool completions

To teach the shell a new tool's subcommands, drop a JSON file in
`src/betterterminal/completions/data/<tool>.json`:

```json
{
  "tool": "mytool",
  "subcommands": {
    "build": "Build the project",
    "deploy": "Deploy the project"
  }
}
```

It is picked up automatically the next time you complete that command.
