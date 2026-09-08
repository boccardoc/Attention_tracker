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

-- Market-wide concentration, one row per day. Answers "is attention broadening or
-- narrowing", which no per-theme z-score can express.
CREATE TABLE IF NOT EXISTS market_concentration (
  date             TEXT NOT NULL,
  hhi              REAL,   -- 1/N = perfectly even .. 1.0 = all on one theme
  top5_share       REAL,
  breadth_early    INTEGER,
  breadth_crowded  INTEGER,
  breadth_froth    INTEGER,
  breadth_dormant  INTEGER,
  PRIMARY KEY (date)
);

-- prices is referenced by the dashboard (Phase 3) but absent from the spec schema;
-- added here so the basket ETF overlay + movers price-change have a source.
CREATE TABLE IF NOT EXISTS prices (
  date   TEXT NOT NULL,
  ticker TEXT NOT NULL,
  close  REAL,
  PRIMARY KEY (date, ticker)
);

-- Where the attention comes FROM: per-theme search interest by country, 0-100 relative
-- within the theme. Refreshed weekly rather than daily (see collect.py) because Trends
-- is the most rate-limit-fragile source and country mix moves slowly.
CREATE TABLE IF NOT EXISTS theme_geo (
  date     TEXT NOT NULL,
  theme_id TEXT NOT NULL,
  country  TEXT NOT NULL,   -- ISO-3166 alpha-2
  interest REAL,
  PRIMARY KEY (date, theme_id, country)
);

-- What large managers HELD, per quarter, from SEC 13F filings. Deliberately separate
-- from the daily attention tables: this is quarterly and up to 135 days stale, so it can
-- never be folded into a daily z-score.
CREATE TABLE IF NOT EXISTS institutional_holdings (
  quarter   TEXT NOT NULL,     -- 13F period of report, e.g. '2026-06-30'
  manager   TEXT NOT NULL,     -- slug from sources/managers.py
  ticker    TEXT NOT NULL,
  value_usd REAL,              -- always whole dollars (units normalised on ingest)
  shares    REAL,
  PRIMARY KEY (quarter, manager, ticker)
);

-- What the sell side is PUBLISHING. Continuous, unlike 13F.
CREATE TABLE IF NOT EXISTS analyst_actions (
  date       TEXT NOT NULL,
  ticker     TEXT NOT NULL,
  firm       TEXT NOT NULL,
  action     TEXT,
  from_grade TEXT,
  to_grade   TEXT,
  PRIMARY KEY (date, ticker, firm, to_grade)
);

CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON institutional_holdings (ticker, quarter);
CREATE INDEX IF NOT EXISTS idx_analyst_ticker  ON analyst_actions (ticker, date);
CREATE INDEX IF NOT EXISTS idx_theme_geo ON theme_geo (theme_id, date);
CREATE INDEX IF NOT EXISTS idx_raw_theme_source ON raw_attention (theme_id, source, date);
CREATE INDEX IF NOT EXISTS idx_scores_theme     ON scores (theme_id, date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker    ON prices (ticker, date);
"""


def db_path() -> Path:
    """Resolve the shared database path (env override or repo default)."""
    env = os.environ.get("ATTENTION_DB")
    return Path(env).expanduser().resolve() if env else _DEFAULT_DB


# Columns added to `scores` after the table first shipped. CREATE TABLE IF NOT EXISTS is
# a no-op on an existing table, so these must be ALTERed in explicitly or an older DB
# (e.g. the accrued Reddit history restored from the data-snapshot branch) would keep the
# old shape and every write would fail.
SCORES_ADDED_COLUMNS = {
    "share_pct": "REAL",               # share of all themes' attention that day
    "sentiment_z": "REAL",
    "sentiment_velocity_7d": "REAL",
}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Add any missing columns to existing tables. Returns the columns added."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(scores)")}
    added = []
    for col, coltype in SCORES_ADDED_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE scores ADD COLUMN {col} {coltype}")
            added.append(col)
    if added:
        conn.commit()
    return added


def connect() -> sqlite3.Connection:
    """Open the DB (creating parent dir + schema on first use, then migrating)."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    migrate(conn)
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
    """rows: (date, theme_id, research_z, speculative_z, research_vel, spec_vel,
    sentiment_z, sentiment_vel, share_pct)."""
    conn.executemany(
        "INSERT OR REPLACE INTO scores "
        "(date, theme_id, research_z, speculative_z, "
        " research_velocity_7d, speculative_velocity_7d, "
        " sentiment_z, sentiment_velocity_7d, share_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def upsert_concentration(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, hhi, top5_share, early, crowded, froth, dormant)."""
    conn.executemany(
        "INSERT OR REPLACE INTO market_concentration "
        "(date, hhi, top5_share, breadth_early, breadth_crowded, "
        " breadth_froth, breadth_dormant) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
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


def upsert_theme_geo(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, theme_id, country, interest). Idempotent overwrite."""
    conn.executemany(
        "INSERT OR REPLACE INTO theme_geo (date, theme_id, country, interest) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def upsert_holdings(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (quarter, manager, ticker, value_usd, shares)."""
    conn.executemany(
        "INSERT OR REPLACE INTO institutional_holdings "
        "(quarter, manager, ticker, value_usd, shares) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def upsert_analyst_actions(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows: (date, ticker, firm, action, from_grade, to_grade)."""
    conn.executemany(
        "INSERT OR REPLACE INTO analyst_actions "
        "(date, ticker, firm, action, from_grade, to_grade) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def latest_holdings_quarter(conn: sqlite3.Connection, manager: str) -> str | None:
    """Newest 13F quarter stored for a manager, used to skip re-downloading."""
    row = conn.execute(
        "SELECT MAX(quarter) FROM institutional_holdings WHERE manager = ?", (manager,)
    ).fetchone()
    return row[0] if row else None


def latest_analyst_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(date) FROM analyst_actions").fetchone()
    return row[0] if row else None


def latest_geo_date(conn: sqlite3.Connection, theme_id: str) -> str | None:
    """Most recent date we have country data for, used to gate the weekly refresh."""
    row = conn.execute(
        "SELECT MAX(date) FROM theme_geo WHERE theme_id = ?", (theme_id,)
    ).fetchone()
    return row[0] if row else None


def fetch_source_series(conn: sqlite3.Connection, theme_id: str, source: str) -> list[tuple]:
    """Return [(date, raw_value), ...] ascending for a theme+source (for normalize)."""
    cur = conn.execute(
        "SELECT date, raw_value FROM raw_attention "
        "WHERE theme_id = ? AND source = ? ORDER BY date ASC",
        (theme_id, source),
    )
    return cur.fetchall()
