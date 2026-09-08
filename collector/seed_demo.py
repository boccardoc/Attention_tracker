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
from sources import sentiment as sentiment_mod

# Synthetic post text, so the demo exercises the REAL VADER code path rather than
# fabricating a sentiment number. Phrasing mirrors how these subreddits actually write.
BULL_POSTS = [
    "{name} is breaking out, this is the catalyst everyone was waiting for",
    "Very bullish on {name} after that upgrade, loading up here",
    "{name} beat expectations and guidance looks strong",
    "Finally some good news for {name}, outperform from here",
    "{name} setup looks great, strong breakout on volume",
]
BEAR_POSTS = [
    "{name} is bearish here, downgraded again and guidance was cut",
    "Total bagholder on {name}, this keeps breaking down",
    "{name} missed badly, dilution risk is real",
    "Awful print for {name}, underperform and no catalyst",
    "{name} looks terrible, breakdown confirmed",
]
NEUTRAL_POSTS = [
    "Anyone have a DD on {name}? Trying to understand the space",
    "What is the consensus on {name} right now",
    "Reading up on {name} this weekend, thoughts?",
    "{name} thread - post your analysis",
]

random.seed(7)
TAXONOMY = Path(__file__).parent / "taxonomy.json"
DAYS = 180
END = date.today()  # always ends "today" so a fresh run/redeploy shows current data
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
                # Generate the day's posts and score them through the real analyzer, so
                # a broken VADER integration fails the demo instead of hiding behind a
                # fabricated number. Tone tracks the theme's tilt, as it would in reality.
                tone = sentiment_mod.score_texts(_day_posts(t["name"], spec_tilt, ramp))
                raw.append((
                    d, t["id"], "reddit_sentiment",
                    tone["compound"] if tone else None,
                ))
    return raw


def _day_posts(name: str, spec_tilt: float, ramp: float) -> list[str]:
    """A day's worth of synthetic posts, skewed bullish/bearish by the theme's tilt."""
    n = random.randint(6, 12)
    bull_bias = 0.5 + 0.28 * max(-1.0, min(1.0, spec_tilt)) * (0.35 + ramp)
    posts = []
    for _ in range(n):
        roll = random.random()
        if roll < 0.22:
            template = random.choice(NEUTRAL_POSTS)
        elif random.random() < bull_bias:
            template = random.choice(BULL_POSTS)
        else:
            template = random.choice(BEAR_POSTS)
        posts.append(template.format(name=name))
    return posts


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


def synth_geo(themes):
    """Synthetic 'where the searches come from' rows.

    Shaped to look like real Trends output rather than uniform noise: the English-query
    bias means the anglophone markets always score highly, while the theme's own curated
    footprint countries get a boost so the two maps are visibly related but not identical
    — which is exactly the comparison the panel exists to show.
    """
    anglo = ["US", "GB", "CA", "AU", "IN", "SG", "ZA", "NZ", "IE", "PH"]
    rows = []
    d = END.isoformat()
    for t in themes:
        scores = {}
        for i, c in enumerate(anglo):
            scores[c] = max(4.0, 100 * (0.85 ** i) * random.uniform(0.55, 1.0))
        for i, c in enumerate(t["geo"]["footprint"]):
            boost = 100 * (0.8 ** i) * random.uniform(0.4, 0.95)
            scores[c] = max(scores.get(c, 0.0), boost)
        top = max(scores.values())
        rows += [
            (d, t["id"], c, round(100 * v / top, 1)) for c, v in scores.items()
        ]
    return rows


def main():
    themes = json.loads(TAXONOMY.read_text())
    conn = db.connect()
    print(f"seeding demo data {START}..{END} for {len(themes)} themes")

    db.upsert_raw(conn, synth_attention(themes))
    db.upsert_prices(conn, synth_prices(themes))
    db.upsert_theme_geo(conn, synth_geo(themes))
    n = collect.recompute_scores(conn, themes, as_of=None)
    print(f"done. {n}/{len(themes)} themes have non-null research_z (latest).")
    conn.close()


if __name__ == "__main__":
    main()
