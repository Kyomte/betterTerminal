"""Fallback: parse `<tool> --help` to extract subcommands.

Caches results to ~/.betterterminal/help-cache/<tool>.json, keyed by tool path mtime
so an upgrade invalidates the cache.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


CACHE_DIR = Path.home() / ".betterterminal" / "help-cache"

# Lines like "  status      Show the working tree status"
# Allow 2+ spaces between the word and the description.
_SUBCOMMAND_LINE = re.compile(r"^\s{2,}([a-z][a-z0-9_\-]{1,30})\s{2,}(.+?)\s*$")


@dataclass
class ParsedHelp:
    tool: str
    subcommands: dict[str, str] = field(default_factory=dict)


def _tool_path(tool: str) -> str | None:
    return shutil.which(tool)


def _cache_path(tool: str) -> Path:
    return CACHE_DIR / f"{tool}.json"


def _cache_fresh(tool: str, bin_path: str) -> dict | None:
    cp = _cache_path(tool)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    try:
        cur_mtime = int(os.path.getmtime(bin_path))
    except OSError:
        return None
    if data.get("mtime") != cur_mtime:
        return None
    return data


def _save_cache(tool: str, bin_path: str, subcommands: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        mtime = int(os.path.getmtime(bin_path))
    except OSError:
        mtime = int(time.time())
    _cache_path(tool).write_text(
        json.dumps(
            {"tool": tool, "mtime": mtime, "subcommands": subcommands},
            indent=2,
        )
    )


def parse_help_output(text: str) -> dict[str, str]:
    """Extract candidate subcommands from a --help blob."""
    found: dict[str, str] = {}
    in_commands_section = False
    for line in text.splitlines():
        stripped = line.strip().lower()
        if not line.strip():
            in_commands_section = False
            continue
        if stripped.endswith("commands:") or stripped in {"commands", "subcommands"}:
            in_commands_section = True
            continue
        # Skip option-looking lines.
        if line.lstrip().startswith("-"):
            continue
        m = _SUBCOMMAND_LINE.match(line)
        if m:
            name, desc = m.group(1), m.group(2)
            # Ignore obvious option-words that slip through.
            if name in {"options", "usage", "examples"}:
                continue
            # Prefer the first description we see, but commands-section wins.
            if name not in found or in_commands_section:
                found[name] = desc
    return found


def parse(tool: str, force: bool = False) -> ParsedHelp | None:
    """Run `tool --help` and parse subcommands. Returns None if tool not found."""
    bin_path = _tool_path(tool)
    if not bin_path:
        return None
    if not force:
        cached = _cache_fresh(tool, bin_path)
        if cached is not None:
            return ParsedHelp(tool=tool, subcommands=cached.get("subcommands", {}))
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ParsedHelp(tool=tool, subcommands={})
    text = proc.stdout + "\n" + proc.stderr
    subcommands = parse_help_output(text)
    _save_cache(tool, bin_path, subcommands)
    return ParsedHelp(tool=tool, subcommands=subcommands)
