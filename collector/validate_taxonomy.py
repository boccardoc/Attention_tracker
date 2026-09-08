#!/usr/bin/env python3
"""Validate taxonomy.json against the theme schema.

Checks structural correctness (required fields, types), uniqueness of theme ids,
basic ticker sanity, and date_added format. Exits non-zero on any failure so it
can gate CI.

Run: python validate_taxonomy.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sources.countries import VALID_ISO2  # noqa: E402

TAXONOMY_PATH = Path(__file__).parent / "taxonomy.json"

REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "category": str,
    "wikipedia_articles": list,
    "gtrends_queries": list,
    "reddit_keywords": list,
    "basket": dict,
    "date_added": str,
    "geo": dict,
}

# Presence is checked against REQUIRED_FIELDS; membership is checked against this. They
# were the same set until `geo` arrived — keeping them separate means a genuinely optional
# field can be added later without it silently becoming mandatory.
ALLOWED_FIELDS = set(REQUIRED_FIELDS)

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# US-listed tickers: 1-5 letters, optional .A/.B class suffix. ADRs fit this too.
TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

MIN_THEMES = 40


def validate():
    errors = []

    if not TAXONOMY_PATH.exists():
        print(f"FAIL: {TAXONOMY_PATH} does not exist", file=sys.stderr)
        return 1

    try:
        data = json.loads(TAXONOMY_PATH.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: taxonomy.json is not valid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, list):
        print("FAIL: taxonomy.json must be a JSON array", file=sys.stderr)
        return 1

    if len(data) < MIN_THEMES:
        errors.append(f"expected >= {MIN_THEMES} themes, found {len(data)}")

    seen_ids = set()
    pri = lambda t, m: errors.append(f"[{t}] {m}")

    for i, theme in enumerate(data):
        tid = theme.get("id", f"<index {i}>") if isinstance(theme, dict) else f"<index {i}>"

        if not isinstance(theme, dict):
            errors.append(f"theme at index {i} is not an object")
            continue

        # Required fields + types
        for field, ftype in REQUIRED_FIELDS.items():
            if field not in theme:
                pri(tid, f"missing required field '{field}'")
            elif not isinstance(theme[field], ftype):
                pri(tid, f"field '{field}' must be {ftype.__name__}, got {type(theme[field]).__name__}")

        # Unknown fields (catch typos)
        for field in theme:
            if field not in ALLOWED_FIELDS:
                pri(tid, f"unknown field '{field}'")

        # id format + uniqueness
        if isinstance(theme.get("id"), str):
            if not ID_RE.match(theme["id"]):
                pri(tid, "id must be kebab-case (lowercase, hyphen-separated)")
            if theme["id"] in seen_ids:
                pri(tid, "duplicate id")
            seen_ids.add(theme["id"])

        # date_added format
        if isinstance(theme.get("date_added"), str) and not DATE_RE.match(theme["date_added"]):
            pri(tid, f"date_added '{theme['date_added']}' must be YYYY-MM-DD")

        # Non-empty string lists
        for field in ("wikipedia_articles", "gtrends_queries", "reddit_keywords"):
            vals = theme.get(field)
            if isinstance(vals, list):
                if len(vals) == 0:
                    pri(tid, f"'{field}' must not be empty")
                for v in vals:
                    if not isinstance(v, str) or not v.strip():
                        pri(tid, f"'{field}' contains a non-string or empty value: {v!r}")

        # gtrends: anchor 'stock market' is added at request time, so max 4 theme queries
        gq = theme.get("gtrends_queries")
        if isinstance(gq, list) and len(gq) > 4:
            pri(tid, f"gtrends_queries has {len(gq)} entries; max 4 (anchor term occupies the 5th slot)")

        # geo validation — a wrong ISO code silently disappears from the world map
        # rather than erroring at runtime, so it has to be caught here.
        geo = theme.get("geo")
        if isinstance(geo, dict):
            extra = set(geo) - {"footprint", "listings"}
            if extra:
                pri(tid, f"geo has unexpected keys: {sorted(extra)}")

            footprint = geo.get("footprint")
            if not isinstance(footprint, list) or not footprint:
                pri(tid, "geo.footprint must be a non-empty list of ISO-3166 alpha-2 codes")
            else:
                if len(footprint) != len(set(footprint)):
                    pri(tid, "geo.footprint contains duplicates")
                for code in footprint:
                    if code not in VALID_ISO2:
                        pri(tid, f"geo.footprint has unknown country code '{code}'")

            listings = geo.get("listings")
            if not isinstance(listings, dict):
                pri(tid, "geo.listings must be an object mapping ticker -> country code")
            else:
                basket_tickers = set()
                b = theme.get("basket")
                if isinstance(b, dict):
                    basket_tickers = set(b.get("stocks") or [])
                    if b.get("etf"):
                        basket_tickers.add(b["etf"])
                for ticker, code in listings.items():
                    if ticker not in basket_tickers:
                        pri(tid, f"geo.listings ticker '{ticker}' is not in the basket")
                    if code not in VALID_ISO2:
                        pri(tid, f"geo.listings['{ticker}'] has unknown country '{code}'")
                for ticker in sorted(basket_tickers - set(listings)):
                    pri(tid, f"geo.listings is missing basket ticker '{ticker}'")

        # basket validation
        basket = theme.get("basket")
        if isinstance(basket, dict):
            extra = set(basket) - {"etf", "stocks"}
            if extra:
                pri(tid, f"basket has unexpected keys: {sorted(extra)}")

            etf = basket.get("etf")
            if etf is not None:
                if not isinstance(etf, str) or not TICKER_RE.match(etf):
                    pri(tid, f"basket.etf '{etf}' is not a valid ticker (or null)")

            stocks = basket.get("stocks")
            if not isinstance(stocks, list):
                pri(tid, "basket.stocks must be a list")
            else:
                if not (3 <= len(stocks) <= 5):
                    pri(tid, f"basket.stocks must have 3-5 tickers, has {len(stocks)}")
                if len(stocks) != len(set(stocks)):
                    pri(tid, "basket.stocks contains duplicates")
                for s in stocks:
                    if not isinstance(s, str) or not TICKER_RE.match(s):
                        pri(tid, f"basket.stocks ticker '{s}' is not a valid US ticker")
        # (basket type already checked above)

    # Report
    if errors:
        print(f"VALIDATION FAILED with {len(errors)} error(s):\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    cats = sorted({t["category"] for t in data})
    print(f"OK: {len(data)} themes validated across {len(cats)} categories.")
    print(f"Categories: {', '.join(cats)}")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
