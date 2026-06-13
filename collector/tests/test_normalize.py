"""Unit tests for the z-score / velocity logic (the riskiest part of the system).

Pure stdlib + pytest; no network, no DB. Run: pytest collector/tests -q
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import normalize  # noqa: E402


def make_series(values, start="2026-01-01"):
    """[(date_str, value), ...] with consecutive daily dates."""
    d0 = date.fromisoformat(start)
    return [((d0 + timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]


def test_insufficient_history_yields_none():
    # 29 points < MIN_HISTORY (30) -> all None
    series = make_series([1.0] * 29)
    z = normalize.zscore_series(series)
    assert all(v is None for v in z.values())


def test_zscore_at_threshold():
    # 30 flat values then a spike; flat std is 0 -> None until variance exists.
    flat = [10.0] * 30
    z = normalize.zscore_series(make_series(flat))
    # std == 0 across the window -> None
    assert z[make_series(flat)[-1][0]] is None


def test_known_zscore_value():
    # Ramp 0..29 keeps the final z well within +/-4 (no winsorizing), so we can check
    # the exact value against the textbook formula.
    import statistics
    window = [float(i) for i in range(30)]
    series = make_series(window)
    expected = (window[-1] - statistics.fmean(window)) / statistics.pstdev(window)
    assert abs(expected) < normalize.WINSOR        # guard: example isn't clamped
    assert abs(z_last(series) - expected) < 1e-9


def z_last(series):
    z = normalize.zscore_series(series)
    return z[series[-1][0]]


def test_winsorize_clamps_at_4():
    # 30 zeros then a massive outlier -> z clamped to +4.
    series = make_series([0.0] * 29 + [1e6])
    assert z_last(series) == 4.0
    # huge negative outlier -> -4
    series_neg = make_series([0.0] * 29 + [-1e6])
    assert z_last(series_neg) == -4.0


def test_null_values_skipped_in_window():
    # Nulls don't count toward the 30-observation requirement.
    vals = [None, None, None] + [1.0] * 29
    series = make_series(vals)
    # only 29 non-null in window -> last is None
    assert z_last(series) is None


def test_current_null_is_none():
    series = make_series([1.0] * 30 + [None])
    assert z_last(series) is None


def test_compose_research_mean_of_available():
    wiki = {"2026-01-01": 2.0, "2026-01-02": None}
    gt = {"2026-01-01": 4.0, "2026-01-02": 1.0}
    res = normalize.compose_research(wiki, gt)
    assert res["2026-01-01"] == 3.0      # mean(2,4)
    assert res["2026-01-02"] == 1.0      # only gtrends available


def test_compose_research_both_none():
    wiki = {"2026-01-01": None}
    gt = {"2026-01-01": None}
    assert normalize.compose_research(wiki, gt)["2026-01-01"] is None


def test_velocity_7d():
    z = {
        "2026-01-01": 0.0,
        "2026-01-08": 2.5,   # exactly 7 days later
    }
    vel = normalize.velocity_7d(z)
    assert vel["2026-01-08"] == 2.5
    assert vel["2026-01-01"] is None     # no prior point 7 days back


def test_velocity_missing_endpoint():
    z = {"2026-01-08": 2.5}  # no 2026-01-01
    assert normalize.velocity_7d(z)["2026-01-08"] is None


def test_compute_theme_scores_shapes():
    wiki = make_series([float(i % 5) for i in range(40)])
    gt = make_series([float((i * 2) % 7) for i in range(40)])
    rd = make_series([float(i % 3) for i in range(40)])
    rows = normalize.compute_theme_scores(wiki, gt, rd)
    last = wiki[-1][0]
    assert set(rows[last]) == {
        "research_z", "speculative_z",
        "research_velocity_7d", "speculative_velocity_7d",
    }
