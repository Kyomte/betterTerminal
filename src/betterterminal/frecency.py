"""zoxide-style frecency tracking for directory jumps.

Frecency = frequency * recency_factor.

recency_factor (matching zoxide's piecewise scheme):
    < 1 hour    -> 4.0
    < 1 day     -> 2.0
    < 1 week    -> 0.5
    older       -> 0.25
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz


DEFAULT_DB_PATH = Path.home() / ".betterterminal" / "frecency.db"


@dataclass
class Visit:
    path: str
    frequency: int
    last_visited: int  # unix seconds

    def frecency(self, now: int) -> float:
        age = max(now - self.last_visited, 0)
        if age < 3600:
            factor = 4.0
        elif age < 86_400:
            factor = 2.0
        elif age < 604_800:
            factor = 0.5
        else:
            factor = 0.25
        return self.frequency * factor


class FrecencyStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                path TEXT PRIMARY KEY,
                frequency INTEGER NOT NULL DEFAULT 1,
                last_visited INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def record(self, path: Path) -> None:
        """Insert or bump a visit for `path` (must be absolute, existing directory)."""
        p = str(path.resolve())
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO visits(path, frequency, last_visited) VALUES(?, 1, ?)
            ON CONFLICT(path) DO UPDATE SET
                frequency = frequency + 1,
                last_visited = excluded.last_visited
            """,
            (p, now),
        )
        self.conn.commit()

    def all_visits(self) -> list[Visit]:
        rows = self.conn.execute(
            "SELECT path, frequency, last_visited FROM visits"
        ).fetchall()
        return [Visit(*r) for r in rows]

    def query(self, needle: str, limit: int = 10) -> list[tuple[Path, float]]:
        """Return paths matching needle, ranked by fuzzy_match * frecency.

        An empty needle returns top entries by raw frecency.
        """
        now = int(time.time())
        visits = self.all_visits()
        scored: list[tuple[Path, float]] = []
        for v in visits:
            # Hide visits whose path no longer exists — but keep them in the DB
            # in case the user later restores the directory.
            if not Path(v.path).is_dir():
                continue
            frec = v.frecency(now)
            if not needle:
                score = frec
            else:
                basename = Path(v.path).name
                base_score = fuzz.partial_ratio(needle.lower(), basename.lower())
                # Require a strong basename match. Full-path matches in long temp
                # paths are noisy, so we don't use them as a primary signal.
                if base_score < 70:
                    continue
                score = base_score * frec / 100.0
            scored.append((Path(v.path), score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def close(self) -> None:
        self.conn.close()
