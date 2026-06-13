# Attention Rotation Monitor

A daily investment **attention-rotation** monitor. It answers three questions in under
a minute:

1. Which investment themes are gaining attention right now?
2. Is that attention **early-stage research** or **late-stage speculation**?
3. What is the investable basket for each theme?

Every theme is measured on **two independent attention channels**, each expressed as a
z-score versus its own trailing 90 days — never blended into one number:

- **research** (top-of-funnel, slow money) = Wikipedia pageviews + Google Trends
- **speculative** (in-the-trade, fast money) = Reddit unique-author mentions

The product is the **gap and divergence** between the two channels.

```
attention_tracker/
  collector/            # Python 3.11 — runs daily, writes SQLite
    taxonomy.json       # 40 themes (the data contract)
    validate_taxonomy.py
    collect.py          # daily run
    backfill.py         # 180d history bootstrap (Wikipedia + Trends + prices)
    seed_demo.py        # DEV ONLY: synthetic data so the dashboard runs offline
    normalize.py        # z-scores, velocity (pure stdlib, unit-tested)
    db.py
    sources/            # wikipedia.py gtrends.py reddit.py prices.py
    tests/
  web/                  # Next.js 14 (app router) + Tailwind + recharts
  data/attention.db     # SQLite — collector writes, web reads (NOT committed)
```

## Setup

### Collector
```bash
cd collector
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # add your Reddit API creds (free "script" app)
python validate_taxonomy.py   # sanity-check the taxonomy
python backfill.py            # 180d of Wikipedia + Trends + prices (first run)
python collect.py             # daily run (idempotent; defaults to last complete UTC day)
pytest tests -q               # unit tests for the z-score / velocity logic
```

Reddit credentials live in `.env` (never committed):
`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
The shared DB path can be overridden with `ATTENTION_DB` (default `<repo>/data/attention.db`).

### Dashboard
```bash
cd web
npm install
# point at the same DB the collector writes (defaults to ../data/attention.db)
npm run dev      # http://localhost:3000
```

### Try it without live data (offline demo)
The live sources (Wikipedia/Trends/Reddit/yfinance) need network. To run the dashboard
without them, seed synthetic-but-structurally-real data through the real pipeline:
```bash
cd collector && python seed_demo.py    # writes ../data/attention.db
cd ../web && npm run dev
```
`seed_demo.py` is the **only** place synthetic data exists — the web app reads solely
from SQLite and contains no mock data.

## Dashboard views
- **Rotation Map** (default): scatter of `speculative_z` (x) vs `research_z` (y), colored
  by category, sized by |7-day combined velocity|. Quadrants: **EARLY ROTATION**
  (high research / low speculation — highlighted), **CROWDED CONSENSUS**, **FROTH / MEME**,
  **DORMANT**. Hover a point for its 14-day trail; click to open detail. Themes whose
  speculative channel is still warming up appear in a side tray.
- **Theme Detail**: `research_z` and `speculative_z` over 180 days with the basket ETF's
  normalized price overlaid, a plain-language divergence callout, and the basket tickers
  as cards (price + 7-day change).
- **Movers**: top 10 by research velocity and top 10 by speculative velocity, side by side,
  with z-scores, a velocity sparkline, and the basket ETF's 7-day price change.

## Adding a theme (and why `date_added` matters)
1. Append an object to `collector/taxonomy.json` matching the existing schema (`id`,
   `name`, `category`, `wikipedia_articles`, `gtrends_queries` (≤4 — the 5th Trends slot
   is the `"stock market"` anchor), `reddit_keywords`, `basket` (`etf` may be `null`),
   `date_added`).
2. Set `date_added` to **today's date** and **never change or backdate it**. It records
   when the theme entered the system, not when the underlying trend started. Z-scores need
   ≥30 days of history; `date_added` is how you reason about which themes are still ramping
   versus fully warmed up. Backdating it silently implies history that was never collected.
3. Run `python validate_taxonomy.py`, then `python backfill.py` to pull history for the
   new theme (Wikipedia + Trends backfill; Reddit accrues forward — see caveats).

## Data caveats (read before trusting a signal)
- **Attention ≠ sentiment.** We count *how much* a theme is discussed, not whether the
  discussion is bullish or bearish. A spike can be panic or euphoria.
- **Google Trends rescaling.** Trends returns values scaled 0–100 *within each request
  window*, so naive daily snapshots aren't comparable across days. We mitigate by always
  including the `"stock market"` anchor and storing the **theme/anchor ratio**, and by
  re-pulling the full window each run and **overwriting** the stored series — one
  internally-consistent scale with no discontinuity at the backfill/live seam.
- **Reddit has no backfill and is submissions-only.** The free API tier can't crawl 24h of
  comments across r/wallstreetbets et al., so we count **unique authors of submissions**
  (title + body) only. History therefore accrues from launch: `speculative_z` is NULL for
  the first ~30 days, and the dashboard shows a **"warming up"** state until then.
- **Reddit keyword noise.** Some keywords are common English words (`gold`, `water`,
  `space`). Unique-author dedup resists bot spam but not semantic ambiguity; the per-theme
  z-score absorbs a stable baseline, but treat low-magnitude speculative moves with caution.
- **Wikipedia publish lag.** Wikimedia publishes pageviews ~24–48h late, so the collector
  aligns to the **last complete UTC day (T-1)**. Reddit is attributed to the same day so a
  row's two channels compare like-for-like.
- **Theme overlap.** Themes share tickers/keywords (e.g. data-center names appear in both
  AI-Infrastructure and Data-Center-REITs), so rotation-map points are not fully
  independent observations.
- **Prices via yfinance** are unofficial and best-effort; failures write nothing and never
  abort a run.

## Operations
- **Idempotent:** re-running `collect.py` for a date overwrites rows, never duplicates.
- **Resilient:** each source is wrapped — one source (or one theme) failing writes NULL
  and logs; it never aborts the run.
- **Scheduling:** `.github/workflows/collect.yml` runs daily at 22:00 UTC (CI job runs the
  validator + unit tests). The binary SQLite file is **not** committed to git (history
  bloat / merge conflicts); the Action persists it via cache + artifact. The authoritative
  production run is a local/single-node cron writing the shared `data/attention.db` that
  the web app reads.
