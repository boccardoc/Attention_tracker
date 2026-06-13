"""Daily close prices via yfinance, for the dashboard's ETF overlay and movers.

yfinance is unofficial and breaks/rate-limits like pytrends, so every call is wrapped:
on failure we return {} and log, and the caller writes nothing/NULLs rather than aborting.
"""
from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger("collector.prices")


def fetch_closes(tickers: list[str], start: date, end: date) -> list[tuple[str, str, float]]:
    """Return [(date, ticker, close), ...] over [start, end] for the given tickers.

    One bulk download for all tickers. Returns [] on any failure.
    """
    tickers = sorted({t for t in tickers if t})
    if not tickers:
        return []
    try:
        import yfinance as yf

        # end is inclusive for us; yfinance end is exclusive, so the caller passes the
        # day after the desired last day, or we add a day here.
        df = yf.download(
            tickers,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception as e:  # noqa: BLE001
        log.error("yfinance download failed: %s", e)
        return []

    if df is None or df.empty:
        return []

    rows: list[tuple[str, str, float]] = []
    try:
        close = df["Close"]
        # Single ticker -> Series; multiple -> DataFrame with ticker columns.
        if hasattr(close, "columns"):
            for ticker in close.columns:
                for ts, val in close[ticker].items():
                    if val == val:  # not NaN
                        rows.append((ts.date().isoformat(), ticker, float(val)))
        else:
            for ts, val in close.items():
                if val == val:
                    rows.append((ts.date().isoformat(), tickers[0], float(val)))
    except Exception as e:  # noqa: BLE001
        log.error("yfinance parse failed: %s", e)
        return []
    return rows


def basket_tickers(theme: dict) -> list[str]:
    """All tickers we care about for a theme: its ETF (if any) + basket stocks."""
    basket = theme.get("basket", {})
    out = list(basket.get("stocks", []))
    if basket.get("etf"):
        out.append(basket["etf"])
    return out
