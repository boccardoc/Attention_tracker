"""Turn raw attention counts into comparable z-scores and velocities.

Pure-Python on purpose (stdlib only) so the riskiest logic in the whole system is
unit-testable without network or heavy deps.

Definitions (per the spec):
  z(d)  = (value(d) - mean(trailing 90d)) / std(trailing 90d)
          emitted only when >= MIN_HISTORY non-null observations exist in the window,
          else NULL; winsorized to +/- WINSOR.
  research_z    = mean of available {wikipedia_z, gtrends_z}
  speculative_z = reddit_z
  velocity_7d   = z(d) - z(d - 7 calendar days)
"""
from __future__ import annotations

import statistics
from datetime import date as _date, datetime, timedelta

MIN_HISTORY = 30          # need >= 30 non-null points before emitting a z-score
WINDOW_DAYS = 90          # trailing window length
WINSOR = 4.0              # clamp z to +/- this
VELOCITY_LAG_DAYS = 7


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
) -> dict[str, dict]:
    """Combine the three raw source series into per-date score rows.

    Returns {date: {research_z, speculative_z, research_velocity_7d,
    speculative_velocity_7d}} for every date present in any source.
    """
    wiki_z = zscore_series(wiki_series)
    gtrends_z = zscore_series(gtrends_series)
    reddit_z = zscore_series(reddit_series)

    research_z = compose_research(wiki_z, gtrends_z)
    speculative_z = dict(reddit_z)

    research_vel = velocity_7d(research_z)
    speculative_vel = velocity_7d(speculative_z)

    all_dates = set(research_z) | set(speculative_z)
    rows: dict[str, dict] = {}
    for d in all_dates:
        rows[d] = {
            "research_z": research_z.get(d),
            "speculative_z": speculative_z.get(d),
            "research_velocity_7d": research_vel.get(d),
            "speculative_velocity_7d": speculative_vel.get(d),
        }
    return rows
