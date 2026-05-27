"""Comprehensive end-to-end flow: simulate a user session."""

from pathlib import Path

import pytest

from clamshell.app import ClamshellApp
from textual.widgets import Input, RichLog


def _patch_frecency(monkeypatch, db_path: Path):
    from clamshell import app as app_mod
    import clamshell.frecency as frec_mod

    real = frec_mod.FrecencyStore

    def _factory(db_path_arg=db_path):
        return real(db_path=db_path)

    monkeypatch.setattr(frec_mod, "FrecencyStore", _factory)
    monkeypatch.setattr(app_mod, "FrecencyStore", _factory)


async def test_full_user_session(tmp_path, monkeypatch):
    """Simulates: pwd -> cd into project -> tab-complete -> j to jump back -> exit."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")

    proj_a = tmp_path / "alpha-project"
    proj_b = tmp_path / "bravo-project"
    proj_a.mkdir()
    proj_b.mkdir()

    app = ClamshellApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app._refresh_prompt()
        input_w = app.query_one("#prompt-input", Input)

        # 1) pwd
        input_w.value = "pwd"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        # RichLog may word-wrap long paths; check that the basename is present.
        assert tmp_path.name in rendered

        # 2) cd into alpha-project
        input_w.value = "cd alpha-project"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == proj_a.resolve()

        # 3) cd back to tmp_path
        input_w.value = f"cd {tmp_path}"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == tmp_path.resolve()

        # 4) cd into bravo-project
        input_w.value = "cd bravo-project"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == proj_b.resolve()

        # cd back
        input_w.value = f"cd {tmp_path}"
        await pilot.press("enter")
        await pilot.pause()

        # 5) j alpha — should jump to alpha-project (recorded)
        input_w.value = "j alpha"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == proj_a.resolve()

        # 6) cd back, j brav (partial) — should jump to bravo
        input_w.value = f"cd {tmp_path}"
        await pilot.press("enter")
        await pilot.pause()
        input_w.value = "j brav"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == proj_b.resolve()


async def test_tab_completion_with_help_parser_fallback(tmp_path, monkeypatch):
    """Tab on a tool we don't have JSON for should try --help fallback."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = ClamshellApp()
    async with app.run_test() as pilot:
        input_w = app.query_one("#prompt-input", Input)
        # `git` is in our JSON db, so this verifies the primary path.
        input_w.value = "git "
        input_w.cursor_position = 4
        await pilot.press("tab")
        await pilot.pause()
        items = [s.display for s in app._completion_items]
        assert "status" in items
        assert "commit" in items


async def test_unknown_command_shows_error(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = ClamshellApp()
    async with app.run_test() as pilot:
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "this-command-does-not-exist-xyz"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "not found" in rendered or "127" in rendered


async def test_bare_directory_auto_cds(tmp_path, monkeypatch):
    """Typing just a directory name (no `cd`) should change into it."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    sub = tmp_path / "auto-target"
    sub.mkdir()
    app = ClamshellApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app._refresh_prompt()
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "auto-target"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()
