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
from sources import managers as managers_mod
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


def synth_institutions(themes):
    """Synthetic 13F holdings for the two most recent quarters.

    Deliberately shaped like the real thing: passive managers hold nearly everything in
    rough proportion to basket size with tiny quarter-on-quarter drift, while active
    managers hold a few themes in size and move them hard. That is exactly the contrast
    the Institutions tab exists to show, so a bug that pooled the two would be visible.
    """
    # back=1 is the last COMPLETED quarter. Using the current quarter would imply a 13F
    # exists for a period that has not ended yet — the filing deadline is 45 days after
    # quarter close, so the newest real data is always at least one full quarter behind.
    quarters = [_quarter_end(END, back=2), _quarter_end(END, back=1)]
    rows = []
    for m in managers_mod.MANAGERS:
        # Active managers are selective; index funds are not.
        if m.style == "passive":
            covered = themes
        else:
            covered = random.sample(themes, random.randint(3, 9))
        for t in covered:
            tickers = prices_mod.basket_tickers(t)
            base = random.uniform(2e8, 4e9) if m.style == "passive" else random.uniform(5e6, 8e8)
            drift = random.uniform(-0.35, 0.45) if m.style != "passive" else random.uniform(-0.04, 0.06)
            for qi, q in enumerate(quarters):
                factor = 1.0 if qi == 0 else (1.0 + drift)
                for tk in tickers:
                    v = base / len(tickers) * factor * random.uniform(0.7, 1.3)
                    rows.append((q, m.slug, tk, round(v, 2), round(v / 50, 0)))
    return rows


def _quarter_end(d, back=0):
    """The end date of the quarter `back` quarters before d's quarter."""
    q = (d.month - 1) // 3 - back
    y = d.year + (q // 4)
    q = q % 4
    month = (q + 1) * 3
    last = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return date(y, month, last).isoformat()


FIRMS = ["JPMorgan", "Goldman Sachs", "Morgan Stanley", "BofA", "Citi", "UBS",
         "Barclays", "Jefferies", "Evercore ISI", "Bernstein", "RBC", "Mizuho"]
GRADES = ["Underweight", "Neutral", "Equal Weight", "Overweight", "Buy", "Hold"]


def synth_analysts(themes):
    """Synthetic rating actions across basket tickers over the last 90 days."""
    rows = []
    tickers = sorted({tk for t in themes for tk in prices_mod.basket_tickers(t)})
    for tk in tickers:
        for _ in range(random.randint(0, 4)):
            d = (END - timedelta(days=random.randint(0, 89))).isoformat()
            action = random.choices(["up", "down", "main", "init"], [4, 3, 2, 1])[0]
            rows.append((
                d, tk, random.choice(FIRMS), action,
                random.choice(GRADES), random.choice(GRADES),
            ))
    # De-duplicate on the table's primary key so the seed is idempotent.
    seen, deduped = set(), []
    for r in rows:
        key = (r[0], r[1], r[2], r[5])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def main():
    themes = json.loads(TAXONOMY.read_text())
    conn = db.connect()
    print(f"seeding demo data {START}..{END} for {len(themes)} themes")

    db.upsert_raw(conn, synth_attention(themes))
    db.upsert_prices(conn, synth_prices(themes))
    db.upsert_theme_geo(conn, synth_geo(themes))
    db.upsert_holdings(conn, synth_institutions(themes))
    db.upsert_analyst_actions(conn, synth_analysts(themes))
    n = collect.recompute_scores(conn, themes, as_of=None)
    print(f"done. {n}/{len(themes)} themes have non-null research_z (latest).")
    conn.close()


if __name__ == "__main__":
    main()
