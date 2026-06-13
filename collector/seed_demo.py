#!/usr/bin/env python3
"""DEV/DEMO ONLY — populate the database with synthetic but structurally-real data.

This exists so the dashboard can be run and reviewed without live network access to
Wikipedia/Trends/Reddit/yfinance. It writes through the REAL db layer and the REAL
normalize/scoring pipeline (collect.recompute_scores) — the web app reads only from
SQLite and contains no mock data. Do NOT run this in production; use collect.py +
backfill.py instead.

It deliberately spreads themes across all four rotation-map quadrants and leaves a few
themes with <30 days of Reddit history to exercise the "warming up" state.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import db
import collect
from sources import prices as prices_mod

random.seed(7)
TAXONOMY = Path(__file__).parent / "taxonomy.json"
DAYS = 180
END = date(2026, 6, 12)
START = END - timedelta(days=DAYS - 1)


def synth_attention(themes):
    raw = []
    warming = set(random.sample([t["id"] for t in themes], 4))  # <30d reddit
    for ti, t in enumerate(themes):
        # Per-theme baselines + a late-window tilt to scatter across quadrants.
        wiki_base = 800 + ti * 40
        research_tilt = random.uniform(-1.5, 1.8)   # late-window drift in research
        spec_tilt = random.uniform(-1.5, 1.8)       # late-window drift in speculation
        reddit_days = random.randint(8, 25) if t["id"] in warming else random.randint(120, 175)
        for i in range(DAYS):
            d = (START + timedelta(days=i)).isoformat()
            ramp = max(0.0, (i - (DAYS - 25)) / 25.0)  # 0 until last 25d, then ->1
            wiki = wiki_base + 180 * math.sin(i / 9) + research_tilt * 220 * ramp + random.gauss(0, 70)
            gt = 0.5 + 0.25 * math.sin(i / 11) + research_tilt * 0.18 * ramp + random.gauss(0, 0.04)
            raw.append((d, t["id"], "wikipedia", max(0.0, wiki)))
            raw.append((d, t["id"], "gtrends", max(0.0, gt)))
            if i >= DAYS - reddit_days:
                base = 12 + ti % 7
                val = base + spec_tilt * 14 * ramp + random.gauss(0, 4)
                raw.append((d, t["id"], "reddit", max(0.0, round(val))))
    return raw


def synth_prices(themes):
    tickers = sorted({tk for t in themes for tk in prices_mod.basket_tickers(t)})
    rows = []
    for tk in tickers:
        price = random.uniform(20, 400)
        drift = random.uniform(-0.0015, 0.0025)
        for i in range(DAYS):
            d = START + timedelta(days=i)
            if d.weekday() >= 5:
                continue  # no weekend trading
            price *= math.exp(drift + random.gauss(0, 0.012))
            rows.append((d.isoformat(), tk, round(price, 2)))
    return rows


def main():
    themes = json.loads(TAXONOMY.read_text())
    conn = db.connect()
    print(f"seeding demo data {START}..{END} for {len(themes)} themes")

    db.upsert_raw(conn, synth_attention(themes))
    db.upsert_prices(conn, synth_prices(themes))
    n = collect.recompute_scores(conn, themes, as_of=None)
    print(f"done. {n}/{len(themes)} themes have non-null research_z (latest).")
    conn.close()


if __name__ == "__main__":
    main()
