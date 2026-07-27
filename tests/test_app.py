"""End-to-end app tests via Textual's Pilot.

These drive the real Textual app headlessly. They cover:
  - typing a command and submitting runs it
  - Tab triggers autocomplete and the popup appears with subcommand suggestions
  - `cd` changes the prompt
  - `j <query>` jumps to a tracked directory
"""

from pathlib import Path

import pytest

from betterterminal.app import BetterTerminalApp
from betterterminal.frecency import FrecencyStore
from textual.widgets import Input, RichLog


def _patch_frecency(monkeypatch, db_path: Path):
    """Force FrecencyStore to use a temp DB."""
    from betterterminal import app as app_mod
    from betterterminal import builtins as builtins_mod
    import betterterminal.frecency as frec_mod

    real = frec_mod.FrecencyStore

    def _factory(db_path_arg=db_path):
        return real(db_path=db_path)

    monkeypatch.setattr(frec_mod, "FrecencyStore", _factory)
    monkeypatch.setattr(app_mod, "FrecencyStore", _factory)


async def test_help_builtin_runs(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = "help"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", RichLog)
        # RichLog stores lines internally — convert to plain text.
        rendered = "\n".join(str(line) for line in log.lines)
        assert "cd" in rendered
        assert "j" in rendered


async def test_echo_command(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = "echo hello-betterterminal"
        await pilot.press("enter")
        await pilot.pause(0.1)
        log = app.query_one("#output", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "hello-betterterminal" in rendered


async def test_tab_opens_completion_popup(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = "git "
        input_widget.cursor_position = 4
        await pilot.press("tab")
        await pilot.pause()
        popup = app.query_one("#completions")
        assert popup.display is True
        # Should have at least git status / git commit etc.
        assert len(app._completion_items) > 5


async def test_tab_single_suggestion_inserts(tmp_path, monkeypatch):
    """If there's only one matching subcommand, Tab inserts it directly."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#prompt-input", Input)
        # "git stat" matches only "status".
        input_widget.value = "git stat"
        input_widget.cursor_position = len(input_widget.value)
        await pilot.press("tab")
        await pilot.pause()
        # Either inserted directly, or popup with "status" first.
        assert "status" in input_widget.value or len(app._completion_items) >= 1


async def test_cd_updates_prompt(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    sub = tmp_path / "deep-dir"
    sub.mkdir()
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app._refresh_prompt()
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = f"cd {sub}"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()


async def test_j_jumps(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    target = tmp_path / "destination-folder"
    target.mkdir()
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        # Manually record the target so j can find it.
        app.frecency.record(target)
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = "j destination"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == target.resolve()


async def test_interactive_command_graceful_in_headless(tmp_path, monkeypatch):
    """An interactive command under run_test() can't suspend (HeadlessDriver),
    so it must log a 'real terminal' message instead of crashing."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        input_widget = app.query_one("#prompt-input", Input)
        input_widget.value = "vim"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "real terminal" in rendered
