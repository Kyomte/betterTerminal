import time
from pathlib import Path

import pytest

from clamshell.frecency import FrecencyStore, Visit


def test_frecency_factors():
    now = 1_000_000
    assert Visit("/x", 3, now - 60).frecency(now) == pytest.approx(12.0)       # <1h
    assert Visit("/x", 3, now - 7200).frecency(now) == pytest.approx(6.0)      # <1d
    assert Visit("/x", 3, now - 3 * 86_400).frecency(now) == pytest.approx(1.5)  # <1w
    assert Visit("/x", 3, now - 30 * 86_400).frecency(now) == pytest.approx(0.75)  # older


def test_record_and_query(tmp_path):
    db = tmp_path / "f.db"
    store = FrecencyStore(db_path=db)

    a = tmp_path / "alpha"
    b = tmp_path / "beta-project"
    c = tmp_path / "ground"
    for p in (a, b, c):
        p.mkdir()
        store.record(p)

    # Bump beta-project so it has higher frequency.
    store.record(b)
    store.record(b)

    results = store.query("beta")
    assert results, "expected a match"
    assert results[0][0] == b.resolve()


def test_query_empty_returns_top(tmp_path):
    db = tmp_path / "f.db"
    store = FrecencyStore(db_path=db)
    p = tmp_path / "only"
    p.mkdir()
    store.record(p)
    results = store.query("")
    assert results
    assert results[0][0] == p.resolve()


def test_missing_dirs_excluded(tmp_path):
    db = tmp_path / "f.db"
    store = FrecencyStore(db_path=db)
    p = tmp_path / "willvanish"
    p.mkdir()
    store.record(p)
    p.rmdir()
    assert store.query("vanish") == []
