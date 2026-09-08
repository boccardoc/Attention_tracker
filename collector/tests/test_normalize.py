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
        "research_z", "speculative_z", "sentiment_z",
        "research_velocity_7d", "speculative_velocity_7d", "sentiment_velocity_7d",
    }


def test_compute_theme_scores_without_sentiment_is_none():
    """Omitting the 4th series must not break older callers."""
    s = make_series([float(i % 5) for i in range(40)])
    rows = normalize.compute_theme_scores(s, s, s)
    assert rows[s[-1][0]]["sentiment_z"] is None


def test_compute_theme_scores_with_sentiment():
    n = 40
    s = make_series([float(i % 5) for i in range(n)])
    sent = make_series([float(i % 11) for i in range(n)])
    rows = normalize.compute_theme_scores(s, s, s, sent)
    assert rows[s[-1][0]]["sentiment_z"] is not None


# ------------------------------------------------------------- concentration layer

def test_attention_share_sums_to_one_per_date():
    """The core invariant: every day's shares partition 100% of attention."""
    data = {
        ("a", "gtrends"): [("2026-01-01", 1.0)],
        ("b", "gtrends"): [("2026-01-01", 3.0)],
        ("a", "reddit"): [("2026-01-01", 10.0)],
        ("b", "reddit"): [("2026-01-01", 10.0)],
        ("a", "wikipedia"): [("2026-01-01", 900.0)],
        ("b", "wikipedia"): [("2026-01-01", 100.0)],
    }
    shares = normalize.attention_share(data)
    assert abs(sum(shares["2026-01-01"].values()) - 1.0) < 1e-9


def test_attention_share_is_absolute_not_relative():
    """A big steady theme must outrank a tiny one -- the thing z-scores cannot do."""
    data = {
        ("big", "reddit"): [("2026-01-01", 5000.0)],
        ("tiny", "reddit"): [("2026-01-01", 9.0)],
    }
    shares = normalize.attention_share(data)["2026-01-01"]
    assert shares["big"] > shares["tiny"]


def test_attention_share_weights_downweight_wikipedia():
    """Wikipedia dominance must not decide the ranking on its own (finding A)."""
    data = {
        # 'wiki_hog' owns Wikipedia; 'real' owns the keyword-scoped sources.
        ("wiki_hog", "wikipedia"): [("2026-01-01", 1000.0)],
        ("real", "wikipedia"): [("2026-01-01", 0.0)],
        ("wiki_hog", "gtrends"): [("2026-01-01", 0.0)],
        ("real", "gtrends"): [("2026-01-01", 1.0)],
        ("wiki_hog", "reddit"): [("2026-01-01", 0.0)],
        ("real", "reddit"): [("2026-01-01", 50.0)],
    }
    shares = normalize.attention_share(data)["2026-01-01"]
    assert shares["real"] > shares["wiki_hog"]
    assert abs(shares["wiki_hog"] - 0.2) < 1e-9   # exactly its wikipedia weight


def test_attention_share_renormalizes_when_a_source_is_missing():
    """One source down must not shrink the day's total below 1.0."""
    data = {
        ("a", "reddit"): [("2026-01-01", 1.0)],
        ("b", "reddit"): [("2026-01-01", 1.0)],
    }
    shares = normalize.attention_share(data)
    assert abs(sum(shares["2026-01-01"].values()) - 1.0) < 1e-9


def test_attention_share_ignores_sentiment_source():
    """Tone is not a quantity of attention; it must never affect share."""
    data = {
        ("a", "reddit"): [("2026-01-01", 10.0)],
        ("a", "reddit_sentiment"): [("2026-01-01", 0.9)],
    }
    shares = normalize.attention_share(data)["2026-01-01"]
    assert shares == {"a": 1.0}


def test_concentration_index_bounds():
    even = {f"t{i}": 1 / 40 for i in range(40)}
    assert abs(normalize.concentration_index(even)["hhi"] - 1 / 40) < 1e-9
    assert normalize.concentration_index({"solo": 1.0})["hhi"] == 1.0


def test_concentration_index_top5():
    shares = {f"t{i}": 0.1 for i in range(10)}
    assert abs(normalize.concentration_index(shares)["top5_share"] - 0.5) < 1e-9


def test_quadrant_breadth_counts_and_skips_nulls():
    day = {
        "early": {"research_z": 1.0, "speculative_z": -1.0},
        "crowded": {"research_z": 1.0, "speculative_z": 1.0},
        "froth": {"research_z": -1.0, "speculative_z": 1.0},
        "dormant": {"research_z": -1.0, "speculative_z": -1.0},
        "warming": {"research_z": 1.0, "speculative_z": None},
    }
    assert normalize.quadrant_breadth(day) == {
        "early": 1, "crowded": 1, "froth": 1, "dormant": 1,
    }
