"""SEC EDGAR 13F-HR reader: what large managers held, per quarter.

WHAT THIS DATA IS, AND IS NOT
A 13F is a quarterly snapshot of a manager's LONG US-LISTED EQUITY positions, filed up to
45 days after quarter end. It therefore tells you where money *sat* 45-135 days ago. It
excludes shorts, bonds, cash, derivatives and non-US listings, so it is a partial view of
any manager's book, and it is never a view of what they are looking at *now*.

TWO LANDMINES HANDLED HERE
1. `value` units changed. Through 2022 the information table reported value in THOUSANDS
   of dollars; from the amended form (2023 onward) it reports WHOLE DOLLARS. Mixing the
   two silently produces figures that are 1000x wrong. `_normalise_value` keys off the
   report period and both branches are unit-tested.
2. A mistyped CIK does not error -- EDGAR happily returns a different firm's entire book,
   which would be invisible downstream. Every fetch asserts the returned entity name
   contains the manager's expected substring before any row is accepted.

EDGAR requires a descriptive User-Agent with contact details and asks for <=10 req/s.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date

import requests

log = logging.getLogger("collector.edgar")

BASE = "https://data.sec.gov"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {
    "User-Agent": "attention-monitor/1.0 (research dashboard; contact: collector@localhost)",
    "Accept-Encoding": "gzip, deflate",
}
SLEEP = 0.15          # SEC asks for <= 10 req/s; stay well under
TIMEOUT = 30

# The form's value column switched from thousands to whole dollars for periods from
# 2023-01-01 onward. See SEC Release 34-95148 / the amended Form 13F instructions.
DOLLAR_UNITS_FROM = "2023-01-01"


class ManagerMismatch(RuntimeError):
    """EDGAR returned a different entity than the registry expected — refuse the data."""


def _get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        time.sleep(SLEEP)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r
    except Exception as e:  # noqa: BLE001 - one filing failing must not abort the run
        log.warning("edgar GET failed %s: %s", url, e)
        return None


def _normalise_value(raw: float, period: str) -> float:
    """Return the position value in whole dollars regardless of filing vintage."""
    if period and period < DOLLAR_UNITS_FROM:
        return raw * 1000.0
    return raw


def list_13f_filings(manager) -> list[dict]:
    """Recent 13F-HR filings for a manager, newest first.

    Raises ManagerMismatch if the CIK does not belong to the expected firm — better a
    loud failure than silently ingesting the wrong institution's holdings.
    """
    resp = _get(f"{BASE}/submissions/CIK{manager.cik_padded}.json")
    if resp is None:
        return []
    data = resp.json()

    entity = (data.get("name") or "").lower()
    if manager.name_contains.lower() not in entity:
        raise ManagerMismatch(
            f"CIK {manager.cik} resolves to {entity!r}, expected something containing "
            f"{manager.name_contains!r} ({manager.name}) — check the registry"
        )

    recent = data.get("filings", {}).get("recent", {})
    out = []
    for form, acc, rpt, filed in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("reportDate", []),
        recent.get("filingDate", []),
    ):
        if form == "13F-HR":
            out.append({"accession": acc, "period": rpt, "filed": filed})
    return out


def _info_table_url(cik: str, accession: str) -> str | None:
    """Locate the information-table XML inside a filing."""
    acc_nodash = accession.replace("-", "")
    resp = _get(f"{ARCHIVES}/{int(cik)}/{acc_nodash}/index.json")
    if resp is None:
        return None
    items = resp.json().get("directory", {}).get("item", [])
    # Prefer an explicit information table; fall back to any XML that is not the header.
    for it in items:
        n = it.get("name", "").lower()
        if n.endswith(".xml") and "infotable" in n:
            return f"{ARCHIVES}/{int(cik)}/{acc_nodash}/{it['name']}"
    for it in items:
        n = it.get("name", "").lower()
        if n.endswith(".xml") and "primary_doc" not in n:
            return f"{ARCHIVES}/{int(cik)}/{acc_nodash}/{it['name']}"
    return None


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml_text: str, period: str) -> list[dict]:
    """Parse a 13F information table into normalised rows.

    Values are converted to whole dollars using the filing period, so callers never have
    to think about the 2023 units change.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("13F info table did not parse: %s", e)
        return []

    rows = []
    for el in root.iter():
        if _strip_ns(el.tag) != "infoTable":
            continue
        rec: dict[str, str] = {}
        for child in el.iter():
            rec[_strip_ns(child.tag)] = (child.text or "").strip()
        try:
            value = float(rec.get("value") or 0)
        except ValueError:
            continue
        try:
            shares = float(rec.get("sshPrnamt") or 0)
        except ValueError:
            shares = 0.0
        name = rec.get("nameOfIssuer", "").strip()
        if not name:
            continue
        rows.append({
            "issuer": name,
            "cusip": rec.get("cusip", "").strip().upper(),
            "value_usd": _normalise_value(value, period),
            "shares": shares,
        })
    return rows


def fetch_holdings(manager, period_hint: str | None = None) -> tuple[str, list[dict]] | None:
    """Fetch a manager's most recent 13F holdings.

    Returns (period, rows) or None. `period_hint` skips the download when we already hold
    that quarter, so a daily run costs one cheap index request per manager.
    """
    try:
        filings = list_13f_filings(manager)
    except ManagerMismatch as e:
        log.error("%s", e)
        return None
    if not filings:
        return None

    latest = filings[0]
    if period_hint and latest["period"] <= period_hint:
        return None  # nothing newer than what we already stored

    url = _info_table_url(manager.cik, latest["accession"])
    if not url:
        log.warning("no info table found for %s %s", manager.slug, latest["accession"])
        return None
    resp = _get(url)
    if resp is None:
        return None

    rows = parse_info_table(resp.text, latest["period"])
    log.info(
        "edgar %s: %d positions for period %s (filed %s)",
        manager.slug, len(rows), latest["period"], latest["filed"],
    )
    return latest["period"], rows


# ------------------------------------------------------------------ issuer matching

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|lp|llc|"
    r"holdings?|group|the|sa|nv|ag|se|adr|ads|cl|class|com|new|shs|reit|trust|"
    r"technologies|technology)\b",
    re.IGNORECASE,
)
_NONWORD = re.compile(r"[^a-z0-9 ]+")


def normalise_issuer(name: str) -> str:
    """Reduce a 13F issuer name to a comparable key.

    '  NVIDIA CORPORATION  ' and 'Nvidia Corp' both collapse to 'nvidia', so a curated
    alias table can be small.
    """
    s = _NONWORD.sub(" ", (name or "").lower())
    s = _SUFFIXES.sub(" ", s)
    return " ".join(s.split())


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Names for holdings SEC's registrant file does not cover: ETFs (filed by their trust,
# not under the fund's ticker) and foreign ADRs. Only entries verified by name are listed;
# anything absent simply goes unmatched and is reported, never guessed.
ISSUER_ALIASES: dict[str, str] = {
    # ADRs
    "taiwan semiconductor manufacturing": "TSM",
    "asml": "ASML",
    "novo nordisk": "NVO",
    "alibaba": "BABA",
    "pdd": "PDD",
    "jd": "JD",
    "baidu": "BIDU",
    "tencent": "TCEHY",
    "byd": "BYDDY",
    "li auto": "LI",
    "toyota motor": "TM",
    "sony": "SONY",
    "mitsubishi ufj financial": "MUFG",
    "honda motor": "HMC",
    "sumitomo mitsui financial": "SMFG",
    "infosys": "INFY",
    "hdfc bank": "HDB",
    "icici bank": "IBN",
    "wipro": "WIT",
    "dr reddys laboratories": "RDY",
    "vale": "VALE",
    "nu": "NU",
    "mercadolibre": "MELI",
    "petroleo brasileiro": "PBR",
    "itau unibanco": "ITUB",
    "lvmh moet hennessy louis vuitton": "LVMUY",
    "ferrari": "RACE",
    "compagnie financiere richemont": "CFRUY",
    "spotify": "SPOT",
    "netease": "NTES",
    "abb": "ABB",
    "stmicroelectronics": "STM",
    "sociedad quimica y minera de chile": "SQM",
    "shopify": "SHOP",
    "arqit quantum": "ARQQ",
    "zim integrated shipping services": "ZIM",
    "frontline": "FRO",
    "scorpio tankers": "STNG",
    "global ship lease": "GSL",
    "teck resources": "TECK",
    "ero copper": "ERO",
    "hudbay minerals": "HBM",
    "barrick": "GOLD",
    "agnico eagle mines": "AEM",
    "franco nevada": "FNV",
    "wheaton precious metals": "WPM",
    "cameco": "CCJ",
    "denison mines": "DNN",
    "lithium americas": "LAC",
    "nutrien": "NTR",
    "d wave quantum": "QBTS",
    "technipfmc": "FTI",
    "solaredge": "SEDG",
}


def build_issuer_index(universe: set[str], company_names: dict[str, str]) -> dict[str, str]:
    """{normalised issuer name -> ticker} for the tickers we actually care about.

    `company_names` is SEC's authoritative ticker -> registrant title map, so the bulk of
    the universe is matched from a real source rather than from hand-typed guesses.
    ISSUER_ALIASES fills the gaps SEC's registrant file does not cover.
    """
    index: dict[str, str] = {}
    for ticker, title in company_names.items():
        if ticker in universe:
            key = normalise_issuer(title)
            if key:
                index.setdefault(key, ticker)
    for key, ticker in ISSUER_ALIASES.items():
        if ticker in universe:
            index[normalise_issuer(key)] = ticker
    return index


def fetch_company_names() -> dict[str, str]:
    """SEC's ticker -> company title map. Returns {} on failure (callers degrade)."""
    resp = _get(COMPANY_TICKERS_URL)
    if resp is None:
        return {}
    try:
        raw = resp.json()
    except Exception as e:  # noqa: BLE001
        log.warning("company_tickers.json did not parse: %s", e)
        return {}
    out: dict[str, str] = {}
    for entry in raw.values():
        t = str(entry.get("ticker", "")).upper()
        title = entry.get("title", "")
        if t and title:
            out[t] = title
    log.info("edgar: loaded %d ticker names from SEC", len(out))
    return out
