"""Google Trends via pytrends.

Two hard problems handled here:

1. Rate limiting (429): exponential backoff with jitter, max 5 retries, plus a 2-5s
   sleep between every request.

2. Window rescaling: pytrends scales interest 0-100 *within each request window*, so
   raw values pulled on different days are NOT comparable. We mitigate by (a) always
   including the anchor term "stock market" in every payload and (b) storing the
   theme/anchor RATIO rather than the raw 0-100. Each run re-pulls the full window and
   the caller OVERWRITES the stored series, keeping one internally-consistent scale and
   avoiding a discontinuity at the backfill/live seam.

Every failure mode is wrapped: on any error we return {} and log, so the run continues
and the caller writes NULLs rather than crashing.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import date

log = logging.getLogger("collector.gtrends")

ANCHOR = "stock market"
MAX_THEME_TERMS = 4            # anchor + 4 = 5, pytrends hard cap
MAX_RETRIES = 5
SLEEP_RANGE = (2.0, 5.0)       # base sleep between requests


def _sleep():
    time.sleep(random.uniform(*SLEEP_RANGE))


def _build_pytrends():
    """Import lazily so the module imports even when pytrends isn't installed."""
    from pytrends.request import TrendReq

    return TrendReq(hl="en-US", tz=0, retries=0, timeout=(10, 30))


def _interest_over_time(pytrends, terms: list[str], timeframe: str):
    """One throttled, retried request. Returns a pandas DataFrame or None on failure."""
    for attempt in range(MAX_RETRIES):
        try:
            pytrends.build_payload(terms, timeframe=timeframe, geo="")
            df = pytrends.interest_over_time()
            _sleep()
            return df
        except Exception as e:  # noqa: BLE001
            wait = (2 ** attempt) + random.uniform(0, 1.5)
            log.warning(
                "gtrends request failed (attempt %d/%d) for %s: %s; backing off %.1fs",
                attempt + 1, MAX_RETRIES, terms, e, wait,
            )
            time.sleep(wait)
    log.error("gtrends giving up on terms %s", terms)
    return None


def fetch_theme_ratio(
    queries: list[str], start: date, end: date,
) -> dict[str, float]:
    """Return {YYYY-MM-DD: ratio} for one theme over [start, end].

    ratio(d) = mean over the theme's queries of (query_value(d) / anchor_value(d)),
    using the anchor to make the 0-100 scale comparable across runs. Returns {} on
    failure so the caller writes NULLs.
    """
    queries = queries[:MAX_THEME_TERMS]
    timeframe = f"{start.isoformat()} {end.isoformat()}"

    try:
        pytrends = _build_pytrends()
    except Exception as e:  # noqa: BLE001 - pytrends missing or endpoint broke
        log.error("gtrends unavailable: %s", e)
        return {}

    df = _interest_over_time(pytrends, [ANCHOR] + queries, timeframe)
    if df is None or df.empty or ANCHOR not in df.columns:
        return {}

    out: dict[str, float] = {}
    for ts, row in df.iterrows():
        anchor_val = row.get(ANCHOR, 0)
        if not anchor_val or anchor_val <= 0:
            continue  # avoid divide-by-zero; this day stays absent -> NULL
        ratios = [row[q] / anchor_val for q in queries if q in df.columns]
        if not ratios:
            continue
        d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        out[d] = sum(ratios) / len(ratios)
    return out
