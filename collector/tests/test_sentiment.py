"""Tests for the VADER sentiment channel.

The point of these is less "does VADER work" (it is a vendored, tested library) and more
"do our guardrails hold": the low-sample gate, the finance lexicon actually being applied,
and matching posts under the same rule the volume channel uses.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from sources import sentiment  # noqa: E402


def test_below_min_posts_returns_none():
    """A daily mean over 2 posts is noise; we emit NULL rather than pretend."""
    assert sentiment.score_texts(["great news"] * (sentiment.MIN_POSTS - 1)) is None


def test_at_min_posts_returns_a_score():
    result = sentiment.score_texts(["great news, very bullish"] * sentiment.MIN_POSTS)
    assert result is not None
    assert result["n_posts"] == sentiment.MIN_POSTS


def test_empty_input_returns_none():
    assert sentiment.score_texts([]) is None


def test_finance_lexicon_is_applied():
    """Stock VADER scores these 0.0 -- the extension is what makes them readable."""
    bull = sentiment.score_texts(["bullish"] * sentiment.MIN_POSTS)
    bear = sentiment.score_texts(["bearish"] * sentiment.MIN_POSTS)
    assert bull["compound"] > 0.3
    assert bear["compound"] < -0.3


def test_position_words_deliberately_absent():
    """puts/calls/long/short flip meaning with the speaker's book, so we must not guess."""
    for word in ("puts", "calls", "long", "short"):
        assert word not in sentiment.FINANCE_LEXICON


def test_direction_separates_bull_from_bear():
    bull = sentiment.score_texts(
        ["{} breaking out, upgraded, strong beat".format(i) for i in range(6)]
    )
    bear = sentiment.score_texts(
        ["{} downgraded, dilution, bankruptcy risk".format(i) for i in range(6)]
    )
    assert bull["compound"] > bear["compound"]


def test_neutral_rate_flags_offtopic_matches():
    """High neutral rate is the tell for keyword false positives (finding E)."""
    result = sentiment.score_texts(["the meeting is at three o'clock"] * 8)
    assert result["neutral_rate"] == 1.0


def test_score_theme_matches_same_posts_as_volume_channel():
    """Tone and volume must never disagree about which posts belong to a theme."""
    cache = [{"author": f"u{i}", "text": "uranium is bullish"} for i in range(6)]
    cache += [{"author": "x", "text": "unrelated chatter about cooking"}]
    result = sentiment.score_theme(cache, ["uranium"])
    assert result is not None
    assert result["n_posts"] == 6  # the cooking post is excluded
    assert result["compound"] > 0


def test_score_theme_below_threshold_returns_none():
    cache = [{"author": "u1", "text": "uranium is bullish"}]
    assert sentiment.score_theme(cache, ["uranium"]) is None
