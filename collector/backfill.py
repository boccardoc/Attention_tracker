#!/usr/bin/env python3
"""One-time history backfill so z-scores work from day one.

Wikipedia and Google Trends both expose history, so we pull 180 days for each. Reddit
CANNOT be backfilled cheaply on the free tier, so the speculative channel accrues only
from launch forward (documented; the dashboard shows a "warming up" state for ~30 days).

Idempotent: writes overwrite by primary key. gtrends history is overwritten wholesale
(consistent-scale series), Wikipedia is written per day from the API's stable history.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import db
from sources import gtrends, prices, wikipedia
from collect import recompute_scores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("backfill")

TAXONOMY = Path(__file__).parent / "taxonomy.json"
DEFAULT_DAYS = 180


def backfill_wikipedia(conn, themes, start: date, end: date) -> None:
    for t in themes:
        try:
            totals = wikipedia.fetch_theme_daily(t["wikipedia_articles"], start, end)
        except Exception as e:  # noqa: BLE001
            log.warning("wikipedia backfill failed for %s: %s", t["id"], e)
            totals = {}
        rows = [(d, t["id"], "wikipedia", v) for d, v in totals.items()]
        if rows:
            db.upsert_raw(conn, rows)
        log.info("wikipedia backfill %s: %d days", t["id"], len(rows))


def backfill_gtrends(conn, themes, start: date, end: date) -> None:
    # Google Trends caps daily granularity at ~270 days; 180 is safe in one window.
    for t in themes:
        try:
            ratios = gtrends.fetch_theme_ratio(t["gtrends_queries"], start, end)
        except Exception as e:  # noqa: BLE001
            log.warning("gtrends backfill failed for %s: %s", t["id"], e)
            ratios = {}
        rows = [(d, t["id"], "gtrends", v) for d, v in ratios.items()]
        if rows:
            db.upsert_raw(conn, rows)
        log.info("gtrends backfill %s: %d days", t["id"], len(rows))


def backfill_prices(conn, themes, start: date, end: date) -> None:
    tickers = sorted({tk for t in themes for tk in prices.basket_tickers(t)})
    rows = prices.fetch_closes(tickers, start, end + timedelta(days=1))
    if rows:
        db.upsert_prices(conn, rows)
    log.info("prices backfill: %d rows for %d tickers", len(rows), len(tickers))


def main():
    ap = argparse.ArgumentParser(description="Backfill 180d of attention history")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = ap.parse_args()

    themes = json.loads(TAXONOMY.read_text())
    end = wikipedia.last_complete_utc_day()
    start = end - timedelta(days=args.days - 1)
    conn = db.connect()
    log.info("backfilling %s..%s (%d themes)", start, end, len(themes))

    for name, fn in (
        ("wikipedia", backfill_wikipedia),
        ("gtrends", backfill_gtrends),
        ("prices", backfill_prices),
    ):
        try:
            fn(conn, themes, start, end)
        except Exception as e:  # noqa: BLE001
            log.error("backfill source %s aborted: %s", name, e)

    n = recompute_scores(conn, themes, as_of=None)  # write every historical date
    log.info("backfill complete; %d/%d themes have non-null research_z latest",
             n, len(themes))
    conn.close()


if __name__ == "__main__":
    main()
