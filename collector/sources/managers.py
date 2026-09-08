"""Which institutions we track, and what their 13F actually means.

WHY EVERY MANAGER CARRIES A `style` TAG
A 13F is a list of what a manager held, not a list of what it believes. BlackRock owns
~7% of almost every large US company because it replicates indices -- reading that as
"BlackRock likes semiconductors" is simply wrong. Treating all filers alike would rank
every theme by index weight and surface nothing. So:

  passive : index replication. Holdings track the benchmark; only large *changes* carry
            any information, and even then mostly reflect fund flows, not a view.
  active  : discretionary stock pickers and multi-strategy funds. Positions reflect real
            decisions, but books turn over fast and some (Citadel, Millennium) carry
            substantial market-making inventory.
  bank    : broker-dealer holding companies. Their 13Fs mix client assets, hedges and
            market-making inventory. Shown because the user asked for them by name, but
            never presented as conviction.

WHY EACH ENTRY REPEATS THE EXPECTED NAME
CIKs are hand-entered. A single wrong digit does not error -- it silently ingests a
completely different firm's book, which would be invisible in the output. `edgar.py`
therefore checks EDGAR's returned entity name against `name_contains` and refuses the
filing on mismatch. Verify additions against
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<cik> before trusting them.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Manager:
    slug: str
    name: str
    cik: str
    style: str          # 'passive' | 'active' | 'bank'
    name_contains: str  # lowercase substring EDGAR's entity name must contain

    @property
    def cik_padded(self) -> str:
        return self.cik.zfill(10)


MANAGERS: list[Manager] = [
    # ---- passive / index giants -------------------------------------------------
    Manager("blackrock", "BlackRock", "1364742", "passive", "blackrock"),
    Manager("vanguard", "Vanguard Group", "102909", "passive", "vanguard"),
    Manager("state-street", "State Street", "93751", "passive", "state street"),
    Manager("geode", "Geode Capital", "1214717", "passive", "geode"),

    # ---- banks / broker-dealers -------------------------------------------------
    Manager("jpmorgan", "JPMorgan Chase", "19617", "bank", "jpmorgan"),
    Manager("goldman", "Goldman Sachs", "886982", "bank", "goldman"),
    Manager("morgan-stanley", "Morgan Stanley", "895421", "bank", "morgan stanley"),
    Manager("ubs", "UBS Group", "1610520", "bank", "ubs"),

    # ---- active managers --------------------------------------------------------
    Manager("fmr", "Fidelity (FMR)", "315066", "active", "fmr"),
    Manager("berkshire", "Berkshire Hathaway", "1067983", "active", "berkshire"),
    Manager("citadel", "Citadel Advisors", "1423053", "active", "citadel"),
    Manager("millennium", "Millennium Management", "1273087", "active", "millennium"),
    Manager("bridgewater", "Bridgewater Associates", "1350694", "active", "bridgewater"),
    Manager("renaissance", "Renaissance Technologies", "1037389", "active", "renaissance"),
    Manager("two-sigma", "Two Sigma", "1179392", "active", "two sigma"),
    Manager("de-shaw", "D. E. Shaw", "1009207", "active", "shaw"),
    Manager("aqr", "AQR Capital", "1167557", "active", "aqr"),
    Manager("tiger-global", "Tiger Global", "1167483", "active", "tiger global"),
    Manager("coatue", "Coatue Management", "1135730", "active", "coatue"),
    Manager("lone-pine", "Lone Pine Capital", "1061165", "active", "lone pine"),
    Manager("baupost", "Baupost Group", "1061768", "active", "baupost"),
    Manager("pershing-square", "Pershing Square", "1336528", "active", "pershing"),
    Manager("point72", "Point72", "1603466", "active", "point72"),
    Manager("elliott", "Elliott Investment Mgmt", "1791786", "active", "elliott"),
    Manager("soros", "Soros Fund Management", "1029160", "active", "soros"),
    Manager("viking", "Viking Global", "1103804", "active", "viking global"),
]

BY_SLUG = {m.slug: m for m in MANAGERS}
STYLES = ("passive", "active", "bank")


def by_style(style: str) -> list[Manager]:
    return [m for m in MANAGERS if m.style == style]
