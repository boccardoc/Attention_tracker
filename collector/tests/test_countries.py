"""Tests for country-code normalisation.

A wrong ISO code does not raise — it silently paints the wrong country on the map or
drops it entirely, so the mapping layer needs real coverage.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sources import countries  # noqa: E402

TAXONOMY = json.loads((Path(__file__).resolve().parent.parent / "taxonomy.json").read_text())


def test_exact_names_map():
    assert countries.to_iso2("United States") == "US"
    assert countries.to_iso2("Canada") == "CA"
    assert countries.to_iso2("Kazakhstan") == "KZ"


def test_case_and_whitespace_insensitive():
    assert countries.to_iso2("  united states  ") == "US"
    assert countries.to_iso2("CANADA") == "CA"


def test_trends_aliases():
    """Trends does not always use the canonical short name."""
    assert countries.to_iso2("United States of America") == "US"
    assert countries.to_iso2("South Korea") == "KR"
    assert countries.to_iso2("Republic of Korea") == "KR"
    assert countries.to_iso2("Czech Republic") == "CZ"
    assert countries.to_iso2("Türkiye") == "TR"


def test_uk_is_gb_not_uk():
    """'UK' is not an ISO-3166 alpha-2 code; the United Kingdom is GB."""
    assert countries.to_iso2("United Kingdom") == "GB"
    assert "UK" not in countries.VALID_ISO2


def test_unknown_returns_none_rather_than_guessing():
    assert countries.to_iso2("Atlantis") is None
    assert countries.to_iso2("") is None
    assert countries.to_iso2(None) is None


def test_every_valid_code_is_two_uppercase_letters():
    for code in countries.VALID_ISO2:
        assert len(code) == 2 and code.isupper() and code.isalpha(), code


def test_every_name_maps_back_to_its_own_code():
    for code, name in countries.ISO2_NAMES.items():
        assert countries.to_iso2(name) == code


# ---------------------------------------------------------------- taxonomy geography

def test_every_theme_has_geo():
    for t in TAXONOMY:
        assert "geo" in t, t["id"]
        assert t["geo"]["footprint"], t["id"]


def test_all_taxonomy_countries_are_known_codes():
    """The web map keys off these codes; an unknown one renders as a blank country."""
    for t in TAXONOMY:
        for code in t["geo"]["footprint"]:
            assert code in countries.VALID_ISO2, (t["id"], code)
        for ticker, code in t["geo"]["listings"].items():
            assert code in countries.VALID_ISO2, (t["id"], ticker, code)


def test_listings_cover_exactly_the_basket():
    for t in TAXONOMY:
        basket = set(t["basket"]["stocks"])
        if t["basket"].get("etf"):
            basket.add(t["basket"]["etf"])
        assert set(t["geo"]["listings"]) == basket, t["id"]


def test_footprints_have_no_duplicates():
    for t in TAXONOMY:
        fp = t["geo"]["footprint"]
        assert len(fp) == len(set(fp)), t["id"]
