"""Sell-side analyst actions: what the banks are publishing, per ticker.

This is the timely counterpart to 13F. A 13F tells you where money sat months ago; an
upgrade tells you what a firm is saying this week. Both are "big financial players", but
they are different claims and the dashboard keeps them apart:

  13F      -> committed capital, quarterly, 45-135 days stale
  analysts -> published opinion, continuous, no capital behind it

Source is yfinance's `upgrades_downgrades`, which carries the FIRM NAME alongside the
action -- that is what makes "where is JPMorgan turning positive" answerable at all.

Caveats worth remembering when reading the output: yfinance is an unofficial scraper and
this endpoint is among its flakier ones; coverage is uneven (small caps and ADRs often
have none); and firm names arrive as free text, so they are normalised below.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

log = logging.getLogger("collector.analysts")

# Actions we treat as directional. yfinance emits lowercase codes; anything else
# (initiations, reiterations) is kept but scores zero.
UPGRADE = "up"
DOWNGRADE = "down"

# Free-text firm names vary ("J.P. Morgan", "JP Morgan Securities"). Normalising lets the
# UI group by house rather than by spelling.
FIRM_ALIASES = {
    "jp morgan": "JPMorgan",
    "j p morgan": "JPMorgan",
    "jpmorgan": "JPMorgan",
    "jpmorgan chase": "JPMorgan",
    "goldman sachs": "Goldman Sachs",
    "morgan stanley": "Morgan Stanley",
    "bank of america": "BofA",
    "bofa securities": "BofA",
    "merrill lynch": "BofA",
    "citigroup": "Citi",
    "citi": "Citi",
    "wells fargo": "Wells Fargo",
    "ubs": "UBS",
    "barclays": "Barclays",
    "deutsche bank": "Deutsche Bank",
    "hsbc": "HSBC",
    "rbc capital": "RBC",
    "rbc capital markets": "RBC",
    "jefferies": "Jefferies",
    "evercore isi": "Evercore ISI",
    "bernstein": "Bernstein",
    "piper sandler": "Piper Sandler",
    "raymond james": "Raymond James",
    "td cowen": "TD Cowen",
    "cowen": "TD Cowen",
    "stifel": "Stifel",
    "truist": "Truist",
    "mizuho": "Mizuho",
    "nomura": "Nomura",
    "bmo capital": "BMO",
    "bmo capital markets": "BMO",
    "scotiabank": "Scotiabank",
    "oppenheimer": "Oppenheimer",
    "wedbush": "Wedbush",
    "keybanc": "KeyBanc",
    "baird": "Baird",
    "guggenheim": "Guggenheim",
    "susquehanna": "Susquehanna",
}


def normalise_firm(name: str) -> str:
    """Collapse spelling variants so 'J.P. Morgan' and 'JP Morgan' group together."""
    if not name:
        return "Unknown"
    key = "".join(c if c.isalnum() or c.isspace() else " " for c in name.lower())
    key = " ".join(key.split())
    if key in FIRM_ALIASES:
        return FIRM_ALIASES[key]
    for alias, canonical in FIRM_ALIASES.items():
        if key.startswith(alias):
            return canonical
    return name.strip()


def fetch_actions(ticker: str, since: date) -> list[dict]:
    """Recent rating actions for one ticker. Returns [] on any failure."""
    try:
        import yfinance as yf

        df = yf.Ticker(ticker).upgrades_downgrades
    except Exception as e:  # noqa: BLE001 - never abort the run for one ticker
        log.debug("analyst fetch failed for %s: %s", ticker, e)
        return []

    if df is None or getattr(df, "empty", True):
        return []

    out = []
    try:
        for grade_date, row in df.iterrows():
            d = getattr(grade_date, "date", lambda: None)()
            if d is None or d < since:
                continue
            out.append({
                "date": d.isoformat(),
                "ticker": ticker,
                "firm": normalise_firm(str(row.get("Firm", ""))),
                "action": str(row.get("Action", "")).lower(),
                "from_grade": str(row.get("FromGrade", "") or ""),
                "to_grade": str(row.get("ToGrade", "") or ""),
            })
    except Exception as e:  # noqa: BLE001
        log.debug("analyst parse failed for %s: %s", ticker, e)
        return []
    return out


def net_score(actions: list[dict]) -> int:
    """Upgrades minus downgrades. Initiations/reiterations count zero, by design —
    they say a firm is paying attention, not which way it leans."""
    return sum(
        1 if a["action"] == UPGRADE else -1 if a["action"] == DOWNGRADE else 0
        for a in actions
    )


def default_since(as_of: date, days: int = 90) -> date:
    return as_of - timedelta(days=days)
