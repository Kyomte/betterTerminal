"""Load hand-written subcommand completions from JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path


@dataclass
class ToolCompletion:
    tool: str
    subcommands: dict[str, str] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


_CACHE: dict[str, ToolCompletion | None] = {}


def load(tool: str) -> ToolCompletion | None:
    """Return the ToolCompletion for `tool`, or None if no JSON exists."""
    if tool in _CACHE:
        return _CACHE[tool]
    try:
        data_pkg = resources.files("betterterminal.completions.data")
        path = data_pkg.joinpath(f"{tool}.json")
        if not path.is_file():
            _CACHE[tool] = None
            return None
        raw = json.loads(path.read_text())
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        _CACHE[tool] = None
        return None
    comp = ToolCompletion(
        tool=raw.get("tool", tool),
        subcommands=raw.get("subcommands", {}),
        flags=raw.get("flags", []),
    )
    _CACHE[tool] = comp
    return comp


def known_tools() -> list[str]:
    """List the tool names we have JSON completions for."""
    data_pkg = resources.files("betterterminal.completions.data")
    out: list[str] = []
    for entry in data_pkg.iterdir():
        name = entry.name
        if name.endswith(".json"):
            out.append(name[:-5])
    return sorted(out)
