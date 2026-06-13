"""Wikipedia pageviews via the Wikimedia REST API (no API key required).

Per theme we sum daily pageviews across its articles, using the `user` access-agent
filter to exclude bots/spiders. A descriptive User-Agent header is mandatory or the
API returns 403.

Date alignment: Wikimedia publishes with a ~24-48h lag, so at collector run time the
current UTC day is incomplete/absent. Callers should request the last COMPLETE UTC day
(T-1) for the daily run; the full history is stable and used by the backfill.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger("collector.wikipedia")

API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{article}/daily/{start}/{end}"
)
HEADERS = {
    "User-Agent": "attention-monitor/1.0 (research dashboard; contact: collector@localhost)"
}
SLEEP = 0.1            # polite delay between requests
TIMEOUT = 30


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


def _fetch_article(article: str, start: date, end: date) -> dict[str, int]:
    """Return {YYYY-MM-DD: views} for one article, or {} on any failure."""
    url = API.format(
        article=urllib.parse.quote(article.replace(" ", "_"), safe=""),
        start=_fmt(start),
        end=_fmt(end),
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 404:
            # No data for this article/range is not fatal.
            log.warning("wikipedia 404 for %r", article)
            return {}
        resp.raise_for_status()
        items = resp.json().get("items", [])
        out: dict[str, int] = {}
        for it in items:
            # timestamp like '2026010100'
            ts = it["timestamp"]
            d = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
            out[d] = int(it["views"])
        return out
    except Exception as e:  # noqa: BLE001 - one article failing must not abort the run
        log.warning("wikipedia fetch failed for %r: %s", article, e)
        return {}


def fetch_theme_daily(articles: list[str], start: date, end: date) -> dict[str, float]:
    """Sum daily pageviews across a theme's articles over [start, end].

    Returns {YYYY-MM-DD: total_views}. Days where every article failed simply won't
    appear; the caller decides how to treat absence (NULL).
    """
    totals: dict[str, float] = {}
    for art in articles:
        daily = _fetch_article(art, start, end)
        for d, v in daily.items():
            totals[d] = totals.get(d, 0.0) + v
        time.sleep(SLEEP)
    return totals


def last_complete_utc_day(now: datetime | None = None) -> date:
    """The most recent fully-published UTC day (T-1)."""
    now = now or datetime.utcnow()
    return now.date() - timedelta(days=1)
