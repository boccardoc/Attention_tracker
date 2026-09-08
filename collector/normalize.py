"""Turn raw attention counts into comparable z-scores and velocities.

Pure-Python on purpose (stdlib only) so the riskiest logic in the whole system is
unit-testable without network or heavy deps.

Definitions (per the spec):
  z(d)  = (value(d) - mean(trailing 90d)) / std(trailing 90d)
          emitted only when >= MIN_HISTORY non-null observations exist in the window,
          else NULL; winsorized to +/- WINSOR.
  research_z    = mean of available {wikipedia_z, gtrends_z}
  speculative_z = reddit_z
  sentiment_z   = z of the mean VADER compound over matched Reddit posts
  velocity_7d   = z(d) - z(d - 7 calendar days)

Z-scores answer "what is unusual for THIS theme versus its own past". They deliberately
destroy cross-theme comparability, so they cannot answer "where is attention concentrated
right now" -- a theme averaging 5 mentions/day that ticks to 9 scores z=+4, while one
averaging 5000/day scores 0. `attention_share` below supplies that missing absolute view:
each theme's share of all themes' attention on a given day.
"""
from __future__ import annotations

import statistics
from datetime import date as _date, datetime, timedelta

MIN_HISTORY = 30          # need >= 30 non-null points before emitting a z-score
WINDOW_DAYS = 90          # trailing window length
WINSOR = 4.0              # clamp z to +/- this
VELOCITY_LAG_DAYS = 7

# Relative trust when blending each source's share into one composite share.
# Wikipedia is down-weighted on purpose: article breadth, not investor interest, drives
# its magnitude (the AI theme carries "Artificial intelligence", uranium carries
# "Yellowcake"). Trends and Reddit are keyword-scoped per theme, so far more comparable.
SHARE_WEIGHTS = {"gtrends": 0.4, "reddit": 0.4, "wikipedia": 0.2}
TOP_N_SHARE = 5           # "top 5 themes hold X% of attention"


def _parse(d: str) -> _date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def zscore_series(series: list[tuple[str, float | None]]) -> dict[str, float | None]:
    """series: [(date_str, value_or_None), ...] ascending. Returns {date_str: z|None}.

    For each date, the trailing window is all non-null values whose date falls within
    [d - (WINDOW_DAYS-1), d] (calendar days, inclusive). The current value must itself
    be non-null to receive a z-score.
    """
    parsed = [(_parse(d), d, v) for d, v in series]
    out: dict[str, float | None] = {}

    for i, (cur_dt, cur_str, cur_val) in enumerate(parsed):
        if cur_val is None:
            out[cur_str] = None
            continue
        window_start = cur_dt - timedelta(days=WINDOW_DAYS - 1)
        window_vals = [
            v for (dt, _s, v) in parsed[: i + 1]
            if v is not None and window_start <= dt <= cur_dt
        ]
        if len(window_vals) < MIN_HISTORY:
            out[cur_str] = None
            continue
        mean = statistics.fmean(window_vals)
        std = statistics.pstdev(window_vals)
        if std == 0:
            out[cur_str] = None
            continue
        z = (cur_val - mean) / std
        out[cur_str] = max(-WINSOR, min(WINSOR, z))
    return out


def compose_research(
    wiki_z: dict[str, float | None],
    gtrends_z: dict[str, float | None],
) -> dict[str, float | None]:
    """research_z = mean of available wikipedia/gtrends z-scores; None if both absent."""
    dates = set(wiki_z) | set(gtrends_z)
    out: dict[str, float | None] = {}
    for d in dates:
        vals = [z for z in (wiki_z.get(d), gtrends_z.get(d)) if z is not None]
        out[d] = statistics.fmean(vals) if vals else None
    return out


def velocity_7d(z_by_date: dict[str, float | None]) -> dict[str, float | None]:
    """velocity(d) = z(d) - z(d - 7 calendar days); None if either endpoint missing."""
    out: dict[str, float | None] = {}
    for d, z in z_by_date.items():
        if z is None:
            out[d] = None
            continue
        prior = (_parse(d) - timedelta(days=VELOCITY_LAG_DAYS)).isoformat()
        pz = z_by_date.get(prior)
        out[d] = (z - pz) if pz is not None else None
    return out


def compute_theme_scores(
    wiki_series: list[tuple[str, float | None]],
    gtrends_series: list[tuple[str, float | None]],
    reddit_series: list[tuple[str, float | None]],
    sentiment_series: list[tuple[str, float | None]] | None = None,
) -> dict[str, dict]:
    """Combine the raw source series into per-date score rows.

    sentiment_series is optional so existing callers keep working; when absent the
    sentiment fields come back as None rather than being omitted.

    Returns {date: {research_z, speculative_z, sentiment_z, research_velocity_7d,
    speculative_velocity_7d, sentiment_velocity_7d}} for every date present in any source.
    """
    wiki_z = zscore_series(wiki_series)
    gtrends_z = zscore_series(gtrends_series)
    reddit_z = zscore_series(reddit_series)
    sentiment_z = zscore_series(sentiment_series or [])

    research_z = compose_research(wiki_z, gtrends_z)
    speculative_z = dict(reddit_z)

    research_vel = velocity_7d(research_z)
    speculative_vel = velocity_7d(speculative_z)
    sentiment_vel = velocity_7d(sentiment_z)

    all_dates = set(research_z) | set(speculative_z) | set(sentiment_z)
    rows: dict[str, dict] = {}
    for d in all_dates:
        rows[d] = {
            "research_z": research_z.get(d),
            "speculative_z": speculative_z.get(d),
            "sentiment_z": sentiment_z.get(d),
            "research_velocity_7d": research_vel.get(d),
            "speculative_velocity_7d": speculative_vel.get(d),
            "sentiment_velocity_7d": sentiment_vel.get(d),
        }
    return rows


# --------------------------------------------------------------- concentration layer

def attention_share(
    series_by_theme_source: dict[tuple[str, str], list[tuple[str, float | None]]],
    weights: dict[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    """Each theme's share of total attention, per day. Answers "where is attention".

    Input is keyed (theme_id, source) -> [(date, raw_value), ...] -- exactly the shape
    db.fetch_source_series returns, collected across every theme.

    Shares are computed WITHIN each source first (raw units differ wildly: pageviews
    ~10^3, gtrends ratios ~0.5, reddit authors ~10^1, so raw values can never be summed
    across sources), then blended using SHARE_WEIGHTS renormalized over whichever sources
    actually reported that day. Because each per-source share map sums to 1 across themes,
    the blend does too.

    Returns {date: {theme_id: share}} with shares summing to ~1.0 per date.
    """
    weights = weights or SHARE_WEIGHTS

    # date -> source -> theme -> value
    by_date: dict[str, dict[str, dict[str, float]]] = {}
    for (theme_id, source), series in series_by_theme_source.items():
        for d, v in series:
            if v is None or v < 0:
                continue
            by_date.setdefault(d, {}).setdefault(source, {})[theme_id] = float(v)

    out: dict[str, dict[str, float]] = {}
    for d, per_source in by_date.items():
        # Only sources we have a weight for and that carry a non-zero total contribute.
        usable = {
            s: vals for s, vals in per_source.items()
            if s in weights and sum(vals.values()) > 0
        }
        if not usable:
            continue
        weight_total = sum(weights[s] for s in usable)
        combined: dict[str, float] = {}
        for s, vals in usable.items():
            source_total = sum(vals.values())
            w = weights[s] / weight_total
            for theme_id, v in vals.items():
                combined[theme_id] = combined.get(theme_id, 0.0) + w * (v / source_total)
        out[d] = combined
    return out


def concentration_index(shares: dict[str, float]) -> dict[str, float]:
    """Herfindahl index and top-N share for one day's share map.

    hhi ranges from 1/N (attention spread perfectly evenly) to 1.0 (all on one theme);
    a rising hhi means attention is NARROWING onto fewer themes.
    """
    vals = sorted((v for v in shares.values() if v > 0), reverse=True)
    return {
        "hhi": sum(v * v for v in vals),
        "top5_share": sum(vals[:TOP_N_SHARE]),
    }


def institutional_by_theme(
    holdings: list[tuple],
    theme_tickers: dict[str, set[str]],
    manager_styles: dict[str, str],
) -> dict[str, dict]:
    """Aggregate 13F holdings up to themes, with the quarter-over-quarter change.

    holdings: (quarter, manager, ticker, value_usd) rows.

    The CHANGE is the point, not the level. Index managers hold nearly everything roughly
    in proportion to its market cap, so a ranking by absolute dollars would just rank
    themes by size and say nothing about interest. Values are also split by manager style
    so passive index replication is never read as conviction.

    Returns {theme_id: {quarter, prev_quarter, total, prev_total, delta,
                        by_style: {style: {value, prev, delta}}}}.
    """
    quarters = sorted({h[0] for h in holdings})
    if not quarters:
        return {}
    latest = quarters[-1]
    prev = quarters[-2] if len(quarters) > 1 else None

    # (theme, quarter, style) -> summed value
    agg: dict[tuple[str, str, str], float] = {}
    for quarter, manager, ticker, value in holdings:
        if quarter not in (latest, prev):
            continue
        style = manager_styles.get(manager, "active")
        for theme_id, tickers in theme_tickers.items():
            if ticker in tickers:
                key = (theme_id, quarter, style)
                agg[key] = agg.get(key, 0.0) + (value or 0.0)

    styles = sorted({s for (_t, _q, s) in agg})
    out: dict[str, dict] = {}
    for theme_id in theme_tickers:
        by_style = {}
        for style in styles:
            cur = agg.get((theme_id, latest, style), 0.0)
            old = agg.get((theme_id, prev, style), 0.0) if prev else 0.0
            if cur or old:
                by_style[style] = {"value": cur, "prev": old, "delta": cur - old}
        if not by_style:
            continue
        total = sum(v["value"] for v in by_style.values())
        prev_total = sum(v["prev"] for v in by_style.values())
        out[theme_id] = {
            "quarter": latest,
            "prev_quarter": prev,
            "total": total,
            "prev_total": prev_total,
            "delta": total - prev_total,
            "by_style": by_style,
        }
    return out


def quadrant_breadth(day_scores: dict[str, dict]) -> dict[str, int]:
    """How many themes sit in each rotation quadrant on one day.

    Mirrors the quadrant split used by the dashboard (web/app/lib/ui.ts): the y axis is
    research_z, the x axis speculative_z. Themes missing either z are not counted.
    """
    counts = {"early": 0, "crowded": 0, "froth": 0, "dormant": 0}
    for s in day_scores.values():
        r, sp = s.get("research_z"), s.get("speculative_z")
        if r is None or sp is None:
            continue
        if r >= 0:
            counts["early" if sp < 0 else "crowded"] += 1
        else:
            counts["dormant" if sp < 0 else "froth"] += 1
    return counts
