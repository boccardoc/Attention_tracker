#!/usr/bin/env python3
"""Daily collector entry point.

Runs once per day. For each theme it gathers raw attention from three sources, writes
one idempotent row per (date, theme, source), recomputes scores, and updates prices.

Alignment: the as-of date is the last complete UTC day (T-1). Wikipedia and Reddit are
both attributed to that calendar day so research/speculative compose on the same date.
Google Trends re-pulls a trailing window and OVERWRITES its stored series each run to
keep one consistent 0-100 scale (see sources/gtrends.py).

Resilience: every source is wrapped. One source (or one theme within a source) failing
writes NULL and logs; it never aborts the run.

Idempotent: re-running for the same date overwrites rows, never duplicates.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import db
import normalize
from sources import gtrends, prices, reddit, sentiment, wikipedia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("collector")

TAXONOMY = Path(__file__).parent / "taxonomy.json"
GTRENDS_WINDOW_DAYS = 90       # trailing window re-pulled & overwritten each run
PRICE_LOOKBACK_DAYS = 10       # enough for 7-day change + a buffer
GEO_REFRESH_DAYS = 7           # country mix moves slowly; don't burn Trends quota daily


def load_themes() -> list[dict]:
    return json.loads(TAXONOMY.read_text())


# --------------------------------------------------------------------------- sources

def collect_wikipedia(conn, themes, as_of: date) -> None:
    """One Wikipedia row per theme for the as-of day (NULL if the theme yields nothing)."""
    rows = []
    for t in themes:
        try:
            totals = wikipedia.fetch_theme_daily(t["wikipedia_articles"], as_of, as_of)
            val = totals.get(as_of.isoformat())
        except Exception as e:  # noqa: BLE001
            log.warning("wikipedia theme %s failed: %s", t["id"], e)
            val = None
        rows.append((as_of.isoformat(), t["id"], "wikipedia", val))
    db.upsert_raw(conn, rows)
    log.info("wikipedia: wrote %d rows", len(rows))


def collect_gtrends(conn, themes, as_of: date) -> None:
    """Re-pull the trailing window per theme and OVERWRITE the stored gtrends series."""
    start = as_of - timedelta(days=GTRENDS_WINDOW_DAYS - 1)
    for t in themes:
        try:
            ratios = gtrends.fetch_theme_ratio(t["gtrends_queries"], start, as_of)
        except Exception as e:  # noqa: BLE001
            log.warning("gtrends theme %s failed: %s", t["id"], e)
            ratios = {}
        if not ratios:
            # Write a NULL for the as-of day so the run records the attempt.
            db.upsert_raw(conn, [(as_of.isoformat(), t["id"], "gtrends", None)])
            continue
        rows = [(d, t["id"], "gtrends", v) for d, v in ratios.items()]
        db.upsert_raw(conn, rows)
    log.info("gtrends: processed %d themes", len(themes))


def collect_reddit(conn, themes, as_of: date) -> None:
    """Fetch posts once, then derive BOTH volume and tone from that single cache.

    Volume (unique authors) and sentiment (mean VADER compound) are written as separate
    sources so they stay independently interpretable; neither costs an extra API call.
    """
    cache = reddit.fetch_post_cache(as_of)
    rows = []
    for t in themes:
        if cache:
            volume = float(reddit.count_unique_authors(cache, t["reddit_keywords"]))
            scored = sentiment.score_theme(cache, t["reddit_keywords"])
            tone = scored["compound"] if scored else None
        else:
            volume = tone = None  # fetch failed entirely -> NULL for all themes
        rows.append((as_of.isoformat(), t["id"], "reddit", volume))
        rows.append((as_of.isoformat(), t["id"], "reddit_sentiment", tone))
    db.upsert_raw(conn, rows)
    scored_n = sum(1 for r in rows if r[2] == "reddit_sentiment" and r[3] is not None)
    log.info("reddit: wrote %d rows (%d themes with sentiment)", len(rows), scored_n)


def collect_geo(conn, themes, as_of: date) -> None:
    """Refresh per-theme country interest, but only for themes whose data is stale.

    This is throttled to weekly on purpose. Trends 429s are the collector's most common
    failure, and doing every theme daily would add ~40 requests (4-7 minutes of enforced
    sleeps) for data whose country mix barely shifts day to day.
    """
    cutoff = (as_of - timedelta(days=GEO_REFRESH_DAYS)).isoformat()
    stale = [
        t for t in themes
        if (db.latest_geo_date(conn, t["id"]) or "") < cutoff
    ]
    if not stale:
        log.info("geo: all %d themes fresh (<%dd), skipping", len(themes), GEO_REFRESH_DAYS)
        return

    log.info("geo: refreshing %d/%d stale themes", len(stale), len(themes))
    for t in stale:
        try:
            regions = gtrends.fetch_theme_regions(t["gtrends_queries"])
        except Exception as e:  # noqa: BLE001
            log.warning("geo theme %s failed: %s", t["id"], e)
            continue
        if not regions:
            continue
        db.upsert_theme_geo(conn, [
            (as_of.isoformat(), t["id"], country, value)
            for country, value in regions.items()
        ])
    log.info("geo: done")


def collect_prices(conn, themes, as_of: date) -> None:
    tickers = sorted({tk for t in themes for tk in prices.basket_tickers(t)})
    start = as_of - timedelta(days=PRICE_LOOKBACK_DAYS)
    # yfinance end is exclusive; +1 day to include as_of.
    rows = prices.fetch_closes(tickers, start, as_of + timedelta(days=1))
    if rows:
        db.upsert_prices(conn, rows)
    log.info("prices: wrote %d rows for %d tickers", len(rows), len(tickers))


# ----------------------------------------------------------------------------- scores

def recompute_scores(conn, themes, as_of: date | None = None) -> int:
    """Recompute scores from all stored raw_attention. Returns themes with non-null research_z.

    If as_of is given, only that date's score rows are written (daily run); otherwise
    every date is written (used by backfill).
    """
    non_null_research = 0

    # Pull every theme's raw series once: per-theme z-scores need them, and the
    # cross-theme share calculation needs them all together.
    raw: dict[tuple[str, str], list] = {}
    for t in themes:
        for source in ("wikipedia", "gtrends", "reddit", "reddit_sentiment"):
            raw[(t["id"], source)] = db.fetch_source_series(conn, t["id"], source)

    # Absolute, cross-theme view: {date: {theme_id: share}}. Sentiment is excluded --
    # it is a tone, not a quantity of attention, so it must not affect share.
    shares = normalize.attention_share({
        k: v for k, v in raw.items() if k[1] in normalize.SHARE_WEIGHTS
    })

    scored_by_theme: dict[str, dict[str, dict]] = {}
    for t in themes:
        scored = normalize.compute_theme_scores(
            raw[(t["id"], "wikipedia")],
            raw[(t["id"], "gtrends")],
            raw[(t["id"], "reddit")],
            raw[(t["id"], "reddit_sentiment")],
        )
        scored_by_theme[t["id"]] = scored

        items = list(scored.items())
        if as_of is not None:
            key = as_of.isoformat()
            items = [(key, scored[key])] if key in scored else []

        rows = [
            (d, t["id"], s["research_z"], s["speculative_z"],
             s["research_velocity_7d"], s["speculative_velocity_7d"],
             s["sentiment_z"], s["sentiment_velocity_7d"],
             shares.get(d, {}).get(t["id"]))
            for d, s in items
        ]
        if rows:
            db.upsert_scores(conn, rows)

        latest_key = as_of.isoformat() if as_of else (max(scored) if scored else None)
        if latest_key and scored.get(latest_key, {}).get("research_z") is not None:
            non_null_research += 1

    _write_concentration(conn, scored_by_theme, shares, as_of)
    return non_null_research


def _write_concentration(conn, scored_by_theme, shares, as_of: date | None) -> None:
    """Market-wide daily rollup: how concentrated is attention, and how broad is it."""
    dates = [as_of.isoformat()] if as_of is not None else sorted(shares)
    rows = []
    for d in dates:
        day_shares = shares.get(d)
        if not day_shares:
            continue
        idx = normalize.concentration_index(day_shares)
        day_scores = {
            tid: scored[d] for tid, scored in scored_by_theme.items() if d in scored
        }
        breadth = normalize.quadrant_breadth(day_scores)
        rows.append((
            d, idx["hhi"], idx["top5_share"],
            breadth["early"], breadth["crowded"],
            breadth["froth"], breadth["dormant"],
        ))
    if rows:
        db.upsert_concentration(conn, rows)
        log.info("concentration: wrote %d day(s)", len(rows))


# ------------------------------------------------------------------------------- main

def run(as_of: date) -> None:
    themes = load_themes()
    conn = db.connect()
    log.info("collecting for as-of date %s (%d themes)", as_of, len(themes))

    # Each wrapped so one source can't abort the run.
    for name, fn in (
        ("wikipedia", collect_wikipedia),
        ("gtrends", collect_gtrends),
        ("reddit", collect_reddit),
        ("geo", collect_geo),
        ("prices", collect_prices),
    ):
        try:
            fn(conn, themes, as_of)
        except Exception as e:  # noqa: BLE001
            log.error("source %s aborted: %s", name, e)

    n = recompute_scores(conn, themes, as_of)
    log.info("scores: %d/%d themes have non-null research_z for %s", n, len(themes), as_of)
    conn.close()


def main():
    ap = argparse.ArgumentParser(description="Daily attention collector")
    ap.add_argument(
        "--date", help="as-of date YYYY-MM-DD (default: last complete UTC day, T-1)"
    )
    args = ap.parse_args()
    as_of = (
        date.fromisoformat(args.date) if args.date
        else wikipedia.last_complete_utc_day()
    )
    run(as_of)


if __name__ == "__main__":
    main()
