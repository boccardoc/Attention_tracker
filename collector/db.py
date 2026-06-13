"""SQLite access layer for the attention monitor.

The collector writes here; the web app reads the same file. The path is resolved
from the ATTENTION_DB env var, falling back to <repo>/data/attention.db, so both
sub-projects can agree on one location regardless of working directory.

All writes are idempotent: re-running the collector for a date overwrites the row
rather than duplicating it (INSERT OR REPLACE on the primary keys).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# collector/db.py -> repo root is one level up
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _REPO_ROOT / "data" / "attention.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_attention (
  date      TEXT NOT NULL,
  theme_id  TEXT NOT NULL,
  source    TEXT NOT NULL,            -- 'wikipedia' | 'gtrends' | 'reddit'
  raw_value REAL,                     -- NULL when the source failed for this date
  PRIMARY KEY (date, theme_id, source)
);

CREATE TABLE IF NOT EXISTS scores (
  date                    TEXT NOT NULL,
  theme_id                TEXT NOT NULL,
  research_z              REAL,
  speculative_z           REAL,
  research_velocity_7d    REAL,
  speculative_velocity_7d REAL,
  PRIMARY KEY (date, theme_id)
);

-- prices is referenced by the dashboard (Phase 3) but absent from the spec schema;
-- added here so the basket ETF overlay + movers price-change have a source.
CREATE TABLE IF NOT EXISTS prices (
  date   TEXT NOT NULL,
  ticker TEXT NOT NULL,
  close  REAL,
  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_raw_theme_source ON raw_attention (theme_id, source, date);
CREATE INDEX IF NOT EXISTS idx_scores_theme     ON scores (theme_id, date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker    ON prices (ticker, date);
"""


def db_path() -> Path:
    """Resolve the shared database path (env override or repo default)."""
    env = os.environ.get("ATTENTION_DB")
    return Path(env).expanduser().resolve() if env else _DEFAULT_DB


def connect() -> sqlite3.Connection:
    """Open the DB (creating parent dir + schema on first use)."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    return conn


def upsert_raw(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, theme_id, source, raw_value). Idempotent overwrite."""
    conn.executemany(
        "INSERT OR REPLACE INTO raw_attention (date, theme_id, source, raw_value) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def upsert_scores(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, theme_id, research_z, speculative_z, research_vel, spec_vel)."""
    conn.executemany(
        "INSERT OR REPLACE INTO scores "
        "(date, theme_id, research_z, speculative_z, "
        " research_velocity_7d, speculative_velocity_7d) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def upsert_prices(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, ticker, close). Idempotent overwrite."""
    conn.executemany(
        "INSERT OR REPLACE INTO prices (date, ticker, close) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def fetch_source_series(conn: sqlite3.Connection, theme_id: str, source: str) -> list[tuple]:
    """Return [(date, raw_value), ...] ascending for a theme+source (for normalize)."""
    cur = conn.execute(
        "SELECT date, raw_value FROM raw_attention "
        "WHERE theme_id = ? AND source = ? ORDER BY date ASC",
        (theme_id, source),
    )
    return cur.fetchall()
