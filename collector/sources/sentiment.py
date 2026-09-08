"""Tone of Reddit discussion, via VADER (github.com/cjhutto/vadersentiment).

This is NOT a fourth data source -- it is a derived measure over text we have already
fetched. `sources/reddit.py` builds a `{author, text}` cache once per run; we score the
posts that match each theme's keywords straight out of that cache, so adding sentiment
costs zero additional API calls.

WHY THIS IS A SEPARATE CHANNEL, NOT A BLEND
The product's whole discipline is that attention volume and its interpretation stay
apart. Concentration answers "where is attention", sentiment answers "how does it feel".
Folding tone into research_z/speculative_z would make both uninterpretable, so sentiment
is scored, stored and displayed on its own.

KNOWN WEAKNESS -- READ BEFORE TRUSTING THIS SIGNAL
VADER is a lexicon/rule model tuned on general social media (Hutto & Gilbert, 2014), not
on financial text. Out of the box it misreads finance in three ways:

  1. Vocabulary gaps: "bullish", "bearish", "bagholder", "rugpull", "dilution" carry no
     valence in the stock lexicon. Partly fixed below by FINANCE_LEXICON.
  2. Position-dependent polarity: "crash", "puts" and "short" are POSITIVE to someone
     positioned short. This is genuinely ambiguous without knowing the speaker's book, so
     we deliberately do NOT add position words to the lexicon -- guessing would be worse
     than staying neutral.
  3. Sarcasm: pervasive on r/wallstreetbets and undetectable by a lexicon model.

Treat the output as a low-confidence, directional overlay. If it proves too noisy the
rigorous upgrades are the Loughran-McDonald finance lexicon or FinBERT.
"""
from __future__ import annotations

import logging

log = logging.getLogger("collector.sentiment")

# Below this many matching posts the daily mean is noise, so we emit NULL instead.
MIN_POSTS = 5

# Conservative finance additions to VADER's lexicon, on its native -4..+4 valence scale.
# Deliberately limited to terms whose direction does not depend on the speaker's
# position; see weakness (2) above for why puts/calls/long/short are absent.
FINANCE_LEXICON = {
    "bullish": 2.4,
    "bearish": -2.4,
    "outperform": 2.0,
    "underperform": -2.0,
    "upgrade": 1.9,
    "upgraded": 1.9,
    "downgrade": -1.9,
    "downgraded": -1.9,
    "beat": 1.8,          # "beat earnings"
    "miss": -1.8,         # "missed earnings"
    "guidance": 0.0,      # neutral on its own; kept so it cannot drift
    "dilution": -2.3,
    "dilutive": -2.3,
    "bankruptcy": -3.4,
    "insolvent": -3.2,
    "delisted": -2.9,
    "bagholder": -2.5,
    "bagholding": -2.5,
    "rugpull": -3.0,
    "rugged": -2.6,
    "halted": -1.8,
    "catalyst": 1.4,
    "breakout": 1.9,
    "breakdown": -1.9,
    "oversold": -1.2,
    "overbought": 0.8,
}

_analyzer = None


def _get_analyzer():
    """Build the VADER analyzer once, with the finance lexicon merged in."""
    global _analyzer
    if _analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        analyzer = SentimentIntensityAnalyzer()
        analyzer.lexicon.update(FINANCE_LEXICON)
        _analyzer = analyzer
    return _analyzer


def score_texts(texts: list[str]) -> dict | None:
    """Mean VADER compound over the given texts, or None below MIN_POSTS.

    Returns {'compound', 'n_posts', 'neutral_rate'}; neutral_rate is a data-quality
    signal -- a high value means VADER found almost nothing it recognised, which is
    exactly what happens when keyword matches are off-topic or heavily sarcastic.
    """
    if len(texts) < MIN_POSTS:
        return None
    try:
        analyzer = _get_analyzer()
    except Exception as e:  # noqa: BLE001 - missing dep must not abort the run
        log.error("vaderSentiment unavailable: %s", e)
        return None

    compounds = []
    for text in texts:
        try:
            compounds.append(analyzer.polarity_scores(text)["compound"])
        except Exception as e:  # noqa: BLE001
            log.warning("vader failed on one post: %s", e)
    if len(compounds) < MIN_POSTS:
        return None

    neutral = sum(1 for c in compounds if abs(c) < 0.05)
    return {
        "compound": sum(compounds) / len(compounds),
        "n_posts": len(compounds),
        "neutral_rate": neutral / len(compounds),
    }


def score_theme(cache: list[dict], keywords: list[str]) -> dict | None:
    """Score the posts in an already-fetched Reddit cache that match a theme.

    Reuses sources.reddit's compiled word-boundary matcher so a post counts toward tone
    under exactly the same rule that counts it toward volume -- the two channels can
    never disagree about which posts belong to a theme.
    """
    from . import reddit  # local import keeps this module importable standalone

    pattern = reddit._compile(keywords)
    texts = [p["text"] for p in cache if pattern.search(p["text"])]
    result = score_texts(texts)
    if result and result["neutral_rate"] > 0.9:
        log.info(
            "sentiment: %d posts but %.0f%% neutral -- likely off-topic keyword matches",
            result["n_posts"], result["neutral_rate"] * 100,
        )
    return result
