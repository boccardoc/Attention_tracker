"""Country reference data for the geography layer.

Two jobs:

1. Google Trends' `interest_by_region` indexes results by ENGLISH COUNTRY NAME
   ("United States", "South Korea"), not by code, so NAME_TO_ISO2 normalises those into
   ISO-3166 alpha-2 before storage. Anything unrecognised is logged and skipped rather
   than guessed at -- a wrong country code is worse than a missing one.

2. VALID_ISO2 is the authority the taxonomy validator checks curated footprints against,
   so a typo like "UK" (not a real ISO code; the United Kingdom is "GB") fails CI instead
   of silently vanishing from the map.

Scope is deliberately the ~90 countries that plausibly appear in these themes, not the
full ISO table -- a complete list would be mostly dead weight and an extra dependency.
The web side keeps its own ISO2 -> numeric map in web/app/lib/countries.ts, because the
world-atlas topology keys countries by ISO numeric id.
"""
from __future__ import annotations

import logging

log = logging.getLogger("collector.countries")

# ISO-3166 alpha-2 -> display name. Single source of truth for what we accept.
ISO2_NAMES: dict[str, str] = {
    "AE": "United Arab Emirates",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "BR": "Brazil",
    "BY": "Belarus",
    "CA": "Canada",
    "CD": "DR Congo",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "EG": "Egypt",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GH": "Ghana",
    "GR": "Greece",
    "HK": "Hong Kong",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IS": "Iceland",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "KW": "Kuwait",
    "KZ": "Kazakhstan",
    "MA": "Morocco",
    "MC": "Monaco",
    "MH": "Marshall Islands",
    "MN": "Mongolia",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NA": "Namibia",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "NO": "Norway",
    "NZ": "New Zealand",
    "PA": "Panama",
    "PE": "Peru",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "UZ": "Uzbekistan",
    "VN": "Vietnam",
    "ZA": "South Africa",
}

VALID_ISO2 = frozenset(ISO2_NAMES)

# Names Google Trends uses that differ from ISO2_NAMES above. The base map is derived
# from ISO2_NAMES, so only the exceptions need listing here.
_TRENDS_ALIASES: dict[str, str] = {
    "united states of america": "US",
    "usa": "US",
    "u.s.": "US",
    "korea": "KR",
    "republic of korea": "KR",
    "south korea": "KR",
    "russian federation": "RU",
    "czech republic": "CZ",
    "viet nam": "VN",
    "uae": "AE",
    "hong kong sar": "HK",
    "hong kong sar china": "HK",
    "macau": "HK",
    "türkiye": "TR",
    "turkiye": "TR",
    "democratic republic of the congo": "CD",
    "congo - kinshasa": "CD",
    "myanmar (burma)": None,          # explicitly out of scope, don't warn about it
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
}

NAME_TO_ISO2: dict[str, str] = {
    name.lower(): code for code, name in ISO2_NAMES.items()
}
NAME_TO_ISO2.update({k: v for k, v in _TRENDS_ALIASES.items() if v is not None})

_IGNORED = {k for k, v in _TRENDS_ALIASES.items() if v is None}
_warned: set[str] = set()


def to_iso2(country_name: str) -> str | None:
    """Normalise a Trends country name to ISO2, or None if we don't recognise it.

    Unknown names are warned about once each (Trends returns ~200 countries and most are
    irrelevant here, so warning every run for every one would drown the logs).
    """
    if not country_name:
        return None
    key = country_name.strip().lower()
    code = NAME_TO_ISO2.get(key)
    if code:
        return code
    if key not in _IGNORED and key not in _warned:
        _warned.add(key)
        log.debug("no ISO2 mapping for Trends country %r — skipping", country_name)
    return None
