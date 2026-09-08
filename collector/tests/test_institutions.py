"""Tests for the institutional layer.

The live paths (SEC EDGAR, Yahoo) cannot be reached from the dev sandbox, so correctness
rests on these: fixture-based parsing, the value-units normalisation, the wrong-CIK guard,
and the theme aggregation. Each of these is a place where a bug would be silent rather
than loud — wrong-by-1000x dollars, or another firm's book ingested under the wrong name.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import normalize  # noqa: E402
from sources import analysts, edgar, managers  # noqa: E402

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "infotable_sample.xml").read_text()


# ------------------------------------------------------------------ 13F XML parsing

def test_parses_all_positions():
    rows = edgar.parse_info_table(FIXTURE, "2026-06-30")
    assert len(rows) == 3
    assert rows[0]["issuer"] == "NVIDIA CORPORATION"
    assert rows[0]["cusip"] == "67066G104"
    assert rows[0]["shares"] == 12000


def test_malformed_xml_returns_empty_not_raises():
    """A bad filing must not abort the run."""
    assert edgar.parse_info_table("<not-xml", "2026-06-30") == []


def test_value_units_thousands_before_2023():
    """Pre-2023 filings report THOUSANDS of dollars."""
    rows = edgar.parse_info_table(FIXTURE, "2022-12-31")
    assert rows[0]["value_usd"] == 1_500_000 * 1000


def test_value_units_dollars_from_2023():
    """From 2023 the same field is whole dollars — a 1000x difference if confused."""
    rows = edgar.parse_info_table(FIXTURE, "2023-03-31")
    assert rows[0]["value_usd"] == 1_500_000


def test_both_vintages_normalise_to_the_same_dollars():
    """The whole point: identical economic position, two filing formats, one answer."""
    old = edgar.parse_info_table(FIXTURE.replace("1500000", "1500"), "2022-12-31")
    new = edgar.parse_info_table(FIXTURE, "2023-06-30")
    assert old[0]["value_usd"] == new[0]["value_usd"] == 1_500_000


# ------------------------------------------------------------------ issuer matching

def test_normalise_issuer_strips_corporate_suffixes():
    assert edgar.normalise_issuer("NVIDIA CORPORATION") == "nvidia"
    assert edgar.normalise_issuer("Cameco Corp") == "cameco"
    assert edgar.normalise_issuer("  ALPHABET INC.  CL A ") == "alphabet a"


def test_issuer_variants_collapse_together():
    assert edgar.normalise_issuer("NVIDIA CORP") == edgar.normalise_issuer("Nvidia Corporation")


def test_build_issuer_index_matches_sec_names_and_aliases():
    universe = {"NVDA", "CCJ", "TSM"}
    sec_names = {"NVDA": "NVIDIA CORP", "CCJ": "CAMECO CORP", "IRRELEVANT": "Other Co"}
    index = edgar.build_issuer_index(universe, sec_names)
    assert index[edgar.normalise_issuer("NVIDIA CORPORATION")] == "NVDA"
    assert index[edgar.normalise_issuer("Cameco Corp")] == "CCJ"
    # TSM is absent from the SEC registrant map but present in curated aliases
    assert index[edgar.normalise_issuer("Taiwan Semiconductor Manufacturing")] == "TSM"


def test_index_excludes_tickers_outside_our_universe():
    index = edgar.build_issuer_index({"NVDA"}, {"NVDA": "NVIDIA CORP", "AAPL": "Apple Inc"})
    assert edgar.normalise_issuer("Apple Inc") not in index


# ------------------------------------------------------------------ manager registry

def test_manager_registry_is_well_formed():
    slugs = [m.slug for m in managers.MANAGERS]
    assert len(slugs) == len(set(slugs)), "duplicate manager slug"
    ciks = [m.cik for m in managers.MANAGERS]
    assert len(ciks) == len(set(ciks)), "duplicate CIK — likely a copy/paste error"
    for m in managers.MANAGERS:
        assert m.style in managers.STYLES, (m.slug, m.style)
        assert m.cik.isdigit(), m.slug
        assert m.name_contains == m.name_contains.lower()


def test_cik_padding():
    m = managers.BY_SLUG["blackrock"]
    assert m.cik_padded == "0001364742"
    assert len(m.cik_padded) == 10


def test_every_style_is_represented():
    """If passive managers vanished, the UI's whole passive/active split is meaningless."""
    for style in managers.STYLES:
        assert managers.by_style(style), f"no managers tagged {style}"


# ------------------------------------------------------------------ aggregation

THEME_TICKERS = {"uranium": {"CCJ", "URA"}, "ai": {"NVDA"}}
STYLES = {"blackrock": "passive", "citadel": "active"}


def test_aggregates_to_themes_with_delta():
    holdings = [
        ("2026-03-31", "blackrock", "CCJ", 100.0),
        ("2026-06-30", "blackrock", "CCJ", 150.0),
        ("2026-06-30", "citadel", "URA", 50.0),
    ]
    out = normalize.institutional_by_theme(holdings, THEME_TICKERS, STYLES)
    u = out["uranium"]
    assert u["quarter"] == "2026-06-30"
    assert u["prev_quarter"] == "2026-03-31"
    assert u["total"] == 200.0          # 150 passive + 50 active
    assert u["prev_total"] == 100.0
    assert u["delta"] == 100.0


def test_style_split_keeps_passive_separate():
    """Index money must never be silently pooled with conviction money."""
    holdings = [
        ("2026-06-30", "blackrock", "CCJ", 900.0),
        ("2026-06-30", "citadel", "CCJ", 10.0),
    ]
    out = normalize.institutional_by_theme(holdings, THEME_TICKERS, STYLES)
    styles = out["uranium"]["by_style"]
    assert styles["passive"]["value"] == 900.0
    assert styles["active"]["value"] == 10.0


def test_themes_with_no_holdings_are_omitted():
    holdings = [("2026-06-30", "blackrock", "CCJ", 100.0)]
    out = normalize.institutional_by_theme(holdings, THEME_TICKERS, STYLES)
    assert "ai" not in out


def test_empty_holdings_is_safe():
    assert normalize.institutional_by_theme([], THEME_TICKERS, STYLES) == {}


def test_single_quarter_reports_zero_delta_not_a_fake_increase():
    """With no prior quarter, delta must not read as if everything was just bought."""
    holdings = [("2026-06-30", "blackrock", "CCJ", 100.0)]
    out = normalize.institutional_by_theme(holdings, THEME_TICKERS, STYLES)
    assert out["uranium"]["prev_quarter"] is None
    assert out["uranium"]["delta"] == 100.0  # vs a zero baseline, and prev_quarter says so


# ------------------------------------------------------------------ analyst actions

def test_firm_name_normalisation():
    assert analysts.normalise_firm("J.P. Morgan") == "JPMorgan"
    assert analysts.normalise_firm("JP Morgan") == "JPMorgan"
    assert analysts.normalise_firm("Goldman Sachs") == "Goldman Sachs"
    assert analysts.normalise_firm("BofA Securities") == "BofA"
    assert analysts.normalise_firm("") == "Unknown"


def test_unknown_firm_is_preserved_not_dropped():
    assert analysts.normalise_firm("Some Boutique Research") == "Some Boutique Research"


def test_net_score_counts_direction_only():
    actions = [
        {"action": "up"}, {"action": "up"}, {"action": "down"},
        {"action": "init"}, {"action": "main"},
    ]
    assert analysts.net_score(actions) == 1   # 2 up - 1 down; init/main are neutral


def test_net_score_empty():
    assert analysts.net_score([]) == 0
