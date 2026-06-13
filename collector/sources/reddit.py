"""Reddit attention via PRAW (free read-only tier).

Scope decision (free tier can't crawl all 24h of comments reliably): we scan recent
SUBMISSIONS (title + selftext) only, across r/stocks, r/investing, r/wallstreetbets,
r/StockMarket, and count UNIQUE AUTHORS per theme (case-insensitive word-boundary
match). Unique authors — not raw mentions — resists bot spam.

Posts are fetched ONCE per run into a cache; every theme is matched against that cache
(no per-theme re-fetch). Comments are intentionally excluded; see README caveats.

Credentials come from .env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, time as dtime, timezone

log = logging.getLogger("collector.reddit")

SUBREDDITS = ["stocks", "investing", "wallstreetbets", "StockMarket"]
PER_SUB_LIMIT = 500            # cap submissions/sub/listing to stay within free tier


def _client():
    """Build a read-only PRAW client from env. Raises if creds/lib missing."""
    import praw  # lazy import

    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    ua = os.environ.get("REDDIT_USER_AGENT")
    if not (cid and secret and ua):
        raise RuntimeError("missing REDDIT_CLIENT_ID/SECRET/USER_AGENT in environment")
    return praw.Reddit(
        client_id=cid, client_secret=secret, user_agent=ua,
        check_for_async=False,
    )


def _day_bounds(target_day) -> tuple[float, float]:
    """[start, end) epoch seconds for a UTC calendar day."""
    start = datetime.combine(target_day, dtime.min, tzinfo=timezone.utc)
    end = datetime.combine(target_day, dtime.max, tzinfo=timezone.utc)
    return start.timestamp(), end.timestamp()


def fetch_post_cache(target_day) -> list[dict]:
    """Fetch submissions for a single UTC calendar day across all subreddits ONCE.

    Attributing Reddit to the same as-of day as Wikipedia keeps a row's research and
    speculative values on the same date so normalize can compose them. Returns
    [{'author': str, 'text': str}], or [] on any failure (caller writes NULLs).
    """
    start_ts, end_ts = _day_bounds(target_day)
    try:
        reddit = _client()
    except Exception as e:  # noqa: BLE001
        log.error("reddit client unavailable: %s", e)
        return []

    cache: list[dict] = []
    for sub in SUBREDDITS:
        try:
            for post in reddit.subreddit(sub).new(limit=PER_SUB_LIMIT):
                if post.created_utc < start_ts:
                    break  # .new() is reverse-chronological; older posts follow
                if post.created_utc > end_ts:
                    continue  # newer than the target day
                author = getattr(post.author, "name", None)
                if not author:
                    continue  # deleted/removed author
                text = f"{post.title or ''} {getattr(post, 'selftext', '') or ''}"
                cache.append({"author": author, "text": text})
        except Exception as e:  # noqa: BLE001 - one sub failing shouldn't kill the rest
            log.warning("reddit fetch failed for r/%s: %s", sub, e)
            continue
    log.info("reddit cache: %d posts across %d subs for %s",
             len(cache), len(SUBREDDITS), target_day)
    return cache


def _compile(keywords: list[str]) -> re.Pattern:
    """Word-boundary, case-insensitive alternation over the theme's keywords."""
    alts = "|".join(re.escape(k) for k in keywords)
    return re.compile(rf"(?<!\w)(?:{alts})(?!\w)", re.IGNORECASE)


def count_unique_authors(cache: list[dict], keywords: list[str]) -> int:
    """Number of distinct authors whose post text matches any keyword."""
    pat = _compile(keywords)
    authors = {p["author"] for p in cache if pat.search(p["text"])}
    return len(authors)


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
