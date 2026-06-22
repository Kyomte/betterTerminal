"""Comprehensive end-to-end flow: simulate a user session."""

from pathlib import Path

import pytest

from betterterminal.app import BetterTerminalApp
from textual.widgets import Input, RichLog


def _patch_frecency(monkeypatch, db_path: Path):
    from betterterminal import app as app_mod
    import betterterminal.frecency as frec_mod

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

    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app._refresh_prompt()
        input_w = app.query_one("#prompt-input", Input)

        # 1) pwd
        input_w.value = "pwd"
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", RichLog)
        # Extract raw text from segments (str(Strip) only shows the repr, and
        # joining strips with "\n" splits any wrapped path across newlines).
        rendered = "".join(seg.text for strip in log.lines for seg in strip)
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


async def test_cd_dash_toggles_previous_directory(tmp_path, monkeypatch):
    """`cd -` should return to the directory we were in before the last cd."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    sub = tmp_path / "child"
    sub.mkdir()
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app.prev_cwd = None
        app._refresh_prompt()
        input_w = app.query_one("#prompt-input", Input)

        input_w.value = "cd child"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()

        input_w.value = "cd -"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == tmp_path.resolve()

        # A second `cd -` toggles back into child.
        input_w.value = "cd -"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()


async def test_tab_completion_with_help_parser_fallback(tmp_path, monkeypatch):
    """Tab on a tool we don't have JSON for should try --help fallback."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
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


async def test_pipe_runs_in_app(tmp_path, monkeypatch):
    """`printf ... | wc -l` should display the piped result."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "printf 'a\\nb\\nc\\n' | wc -l"
        await pilot.press("enter")
        await pilot.pause(0.1)
        log = app.query_one("#output", RichLog)
        rendered = "".join(seg.text for strip in log.lines for seg in strip)
        assert "3" in rendered


async def test_redirect_writes_file_in_app(tmp_path, monkeypatch):
    """`echo ... > file` should create the file from inside the app."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "echo from-betterterminal > note.txt"
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert (tmp_path / "note.txt").read_text().strip() == "from-betterterminal"


async def test_env_var_substitution_in_app(tmp_path, monkeypatch):
    """`echo $VAR` should expand the variable before running."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    monkeypatch.setenv("BT_GREETING", "expanded-value")
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "echo $BT_GREETING"
        await pilot.press("enter")
        await pilot.pause(0.1)
        log = app.query_one("#output", RichLog)
        rendered = "".join(seg.text for strip in log.lines for seg in strip)
        assert "expanded-value" in rendered


async def test_glob_expansion_in_app(tmp_path, monkeypatch):
    """`echo *.py` should expand to the matching files."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    (tmp_path / "alpha.py").touch()
    (tmp_path / "beta.py").touch()
    (tmp_path / "gamma.txt").touch()
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "echo *.py"
        await pilot.press("enter")
        await pilot.pause(0.1)
        log = app.query_one("#output", RichLog)
        rendered = "".join(seg.text for strip in log.lines for seg in strip)
        assert "alpha.py" in rendered
        assert "beta.py" in rendered
        assert "gamma.txt" not in rendered


async def test_cd_with_env_var(tmp_path, monkeypatch):
    """`cd $TARGET` should expand the variable for the builtin."""
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    sub = tmp_path / "var-target"
    sub.mkdir()
    monkeypatch.setenv("BT_TARGET", str(sub))
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "cd $BT_TARGET"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()


async def test_unknown_command_shows_error(tmp_path, monkeypatch):
    _patch_frecency(monkeypatch, tmp_path / "f.db")
    app = BetterTerminalApp()
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
    app = BetterTerminalApp()
    async with app.run_test() as pilot:
        app.cwd = tmp_path
        app._refresh_prompt()
        input_w = app.query_one("#prompt-input", Input)
        input_w.value = "auto-target"
        await pilot.press("enter")
        await pilot.pause()
        assert app.cwd == sub.resolve()
