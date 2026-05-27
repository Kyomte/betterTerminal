"""The Textual app — wires UI, parser, executor, builtins, completer together."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Input, ListItem, ListView, RichLog, Static, Label

from clamshell import builtins
from clamshell.completer import Suggestion, suggest
from clamshell.executor import run_external
from clamshell.frecency import FrecencyStore
from clamshell.parser import ParseError, tokenize


class CompletionList(ListView):
    """ListView that ignores Enter so the Input still owns submit."""

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
    ]

    def action_dismiss(self) -> None:
        self.display = False
        self.app.query_one("#prompt-input", Input).focus()


class ClamshellApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #output {
        height: 1fr;
        border: tall $panel;
        padding: 0 1;
    }
    #completions {
        height: auto;
        max-height: 10;
        display: none;
        background: $boost;
        border: tall $accent;
    }
    #completions.visible {
        display: block;
    }
    #prompt-row {
        height: 3;
        layout: horizontal;
        border: tall $primary;
    }
    #cwd-label {
        width: auto;
        padding: 0 1;
        background: $primary;
        color: $text;
        content-align: left middle;
    }
    #prompt-input {
        width: 1fr;
        border: none;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False),
        Binding("tab", "complete", "Complete", show=False, priority=True),
        Binding("escape", "close_popup", "Close popup", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cwd: Path = Path.cwd()
        self.frecency = FrecencyStore()
        # Record the starting cwd so `j` has at least one entry on first run.
        self.frecency.record(self.cwd)
        self._completion_items: list[Suggestion] = []

    # ----- compose -----

    def compose(self) -> ComposeResult:
        yield RichLog(id="output", highlight=True, markup=False, wrap=True)
        yield CompletionList(id="completions")
        with Container(id="prompt-row"):
            yield Label(self._prompt_text(), id="cwd-label")
            yield Input(placeholder="type a command — try `help`", id="prompt-input")

    def on_mount(self) -> None:
        log = self.query_one("#output", RichLog)
        log.write(Text("clamshell v0.1 — type `help` for built-ins, Tab to complete\n", style="bold cyan"))
        self.query_one("#prompt-input", Input).focus()

    # ----- helpers -----

    def _prompt_text(self) -> str:
        home = str(Path.home())
        s = str(self.cwd)
        if s == home:
            s = "~"
        elif s.startswith(home + "/"):
            s = "~" + s[len(home):]
        return f" {s} "

    def _refresh_prompt(self) -> None:
        self.query_one("#cwd-label", Label).update(self._prompt_text())

    def _log_input(self, line: str) -> None:
        log = self.query_one("#output", RichLog)
        log.write(Text(f"{self._prompt_text().strip()} $ {line}", style="bold green"))

    def _log_output(self, text: str, style: str | None = None) -> None:
        if not text:
            return
        log = self.query_one("#output", RichLog)
        if style:
            log.write(Text(text.rstrip("\n"), style=style))
        else:
            log.write(text.rstrip("\n"))

    # ----- command pipeline -----

    @on(Input.Submitted, "#prompt-input")
    def on_submit(self, event: Input.Submitted) -> None:
        line = event.value
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.value = ""
        self._hide_completions()
        if not line.strip():
            return
        self._log_input(line)
        self._run_line(line)

    def _run_line(self, line: str) -> None:
        try:
            argv = tokenize(line)
        except ParseError as exc:
            self._log_output(f"parse error: {exc}\n", style="red")
            return
        if not argv:
            return

        if builtins.is_builtin(argv[0]):
            result = builtins.run_builtin(self, argv)
            self._log_output(result.output)
            if result.error:
                self._log_output(result.error, style="red")
            if result.new_cwd is not None:
                self.cwd = result.new_cwd
                self._refresh_prompt()
            if result.exit:
                self.frecency.close()
                self.exit()
            return

        # Bare directory? Auto-cd convenience.
        if len(argv) == 1:
            candidate = (self.cwd / argv[0]).expanduser()
            if not Path(argv[0]).is_absolute():
                candidate = self.cwd / argv[0]
            else:
                candidate = Path(argv[0])
            if candidate.is_dir():
                result = builtins.run_builtin(self, ["cd", argv[0]])
                if result.new_cwd:
                    self.cwd = result.new_cwd
                    self._refresh_prompt()
                if result.error:
                    self._log_output(result.error, style="red")
                return

        result = run_external(argv, self.cwd)
        if result.stdout:
            self._log_output(result.stdout)
        if result.stderr:
            self._log_output(result.stderr, style="red")
        if result.returncode != 0 and not result.stderr:
            self._log_output(f"[exit {result.returncode}]", style="dim red")

    # ----- completion -----

    def action_complete(self) -> None:
        input_widget = self.query_one("#prompt-input", Input)
        popup = self.query_one("#completions", CompletionList)

        if popup.display and self._completion_items:
            # Already open: accept the highlighted entry.
            self._accept_current_completion()
            return

        suggestions = suggest(input_widget.value, input_widget.cursor_position, self.cwd)
        if not suggestions:
            return

        # If there's exactly one suggestion, insert it directly.
        if len(suggestions) == 1:
            self._insert_completion(suggestions[0])
            return

        # Common prefix optimization: if all suggestions share a longer prefix,
        # extend the input to that prefix without forcing the user to scroll.
        common = _common_prefix([s.display.rstrip("/") for s in suggestions])
        token_start = _token_start(input_widget.value, input_widget.cursor_position)
        current = input_widget.value[token_start:input_widget.cursor_position]
        # Strip trailing "/" off current for comparison
        cur_for_compare = current.rsplit("/", 1)[-1] if "/" in current else current
        if common and len(common) > len(cur_for_compare):
            base = current[: len(current) - len(cur_for_compare)]
            self._replace_token(base + common)

        self._show_completions(suggestions)

    def _show_completions(self, suggestions: list[Suggestion]) -> None:
        popup = self.query_one("#completions", CompletionList)
        popup.clear()
        self._completion_items = suggestions
        for s in suggestions[:50]:
            label_text = Text()
            label_text.append(s.display, style="bold")
            if s.description:
                label_text.append("  " + s.description, style="dim")
            popup.append(ListItem(Static(label_text)))
        popup.display = True
        popup.add_class("visible")
        popup.index = 0

    def _hide_completions(self) -> None:
        popup = self.query_one("#completions", CompletionList)
        popup.display = False
        popup.remove_class("visible")
        self._completion_items = []

    def action_close_popup(self) -> None:
        self._hide_completions()
        self.query_one("#prompt-input", Input).focus()

    @on(ListView.Selected, "#completions")
    def on_completion_selected(self, event: ListView.Selected) -> None:
        self._accept_current_completion()

    def _accept_current_completion(self) -> None:
        popup = self.query_one("#completions", CompletionList)
        idx = popup.index
        if idx is None or idx < 0 or idx >= len(self._completion_items):
            return
        suggestion = self._completion_items[idx]
        self._insert_completion(suggestion)
        self._hide_completions()
        self.query_one("#prompt-input", Input).focus()

    def _insert_completion(self, s: Suggestion) -> None:
        self._replace_token(s.text)

    def _replace_token(self, replacement: str) -> None:
        input_widget = self.query_one("#prompt-input", Input)
        value = input_widget.value
        cursor = input_widget.cursor_position
        start = _token_start(value, cursor)
        # Find the end of the current token (up to next whitespace).
        end = cursor
        while end < len(value) and not value[end].isspace():
            end += 1
        new_value = value[:start] + replacement + value[end:]
        input_widget.value = new_value
        input_widget.cursor_position = start + len(replacement)

    def action_interrupt(self) -> None:
        input_widget = self.query_one("#prompt-input", Input)
        if input_widget.value:
            input_widget.value = ""
            self._hide_completions()
        else:
            # On empty line, Ctrl-C exits.
            self.frecency.close()
            self.exit()


def _token_start(value: str, cursor: int) -> int:
    if cursor > len(value):
        cursor = len(value)
    start = cursor
    while start > 0 and not value[start - 1].isspace():
        start -= 1
    return start


def _common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    s1 = min(strings)
    s2 = max(strings)
    for i, ch in enumerate(s1):
        if ch != s2[i]:
            return s1[:i]
    return s1
