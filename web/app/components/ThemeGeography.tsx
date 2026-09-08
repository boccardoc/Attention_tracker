"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { ThemeData } from "../lib/types";
import { COUNTRIES, countryName } from "../lib/countries";

// react-simple-maps pulls in d3-geo, which is client-only; prerendering it during
// `next build` (static export) would fail, so it is loaded without SSR.
const GeoMap = dynamic(() => import("./GeoMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[190px] rounded border border-edge bg-panel2" />
  ),
});

/**
 * "Where and what countries are involved" for the selected theme, as two maps:
 *
 *   left  — where the industry physically operates (curated, ordered by significance)
 *   right — where people are searching for it (Google Trends, live)
 *
 * They are shown together deliberately: the gap between them is informative. Attention
 * arriving from countries the industry has no presence in usually means the theme is
 * being traded as a narrative rather than followed as an industry.
 */
export default function ThemeGeography({ theme }: { theme: ThemeData }) {
  const footprint = theme.geo?.footprint ?? [];
  const listings = theme.geo?.listings ?? {};

  // Curated list is RANKED, not weighted — we never claimed "35% Kazakhstan". Convert
  // rank to a decaying weight purely so the map can shade it.
  const footprintValues = useMemo(() => {
    const out: Record<string, number> = {};
    footprint.forEach((c, i) => {
      out[c] = Math.pow(0.75, i);
    });
    return out;
  }, [footprint]);

  const interestValues = useMemo(() => {
    const out: Record<string, number> = {};
    const max = Math.max(...theme.geoInterest.map((g) => g.interest), 0);
    if (max > 0) {
      for (const g of theme.geoInterest) out[g.country] = g.interest / max;
    }
    return out;
  }, [theme.geoInterest]);

  // Which tickers sit in each country — the concrete "what is involved" answer.
  const tickersByCountry = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const [ticker, code] of Object.entries(listings)) {
      (out[code] ??= []).push(ticker);
    }
    for (const list of Object.values(out)) list.sort();
    return out;
  }, [listings]);

  const topInterest = theme.geoInterest.slice(0, 8);

  // Countries too small to exist in the 110m topology still belong in the list.
  const unmappable = footprint.filter((c) => !COUNTRIES[c]?.numeric);

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 text-xs font-semibold text-muted">GEOGRAPHY</div>
        <div className="text-[11px] text-muted">
          Where the industry operates, next to where the searching happens. A theme drawing
          attention from countries it has no presence in is being traded as a story rather
          than followed as an industry.
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* ---------------- industry footprint ---------------- */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 flex items-baseline justify-between gap-2">
            <span className="text-xs font-semibold" style={{ color: "#5eead4" }}>
              INDUSTRY FOOTPRINT
            </span>
            <span className="text-[10px] text-muted">curated · ranked</span>
          </div>
          <GeoMap
            values={footprintValues}
            accent="#5eead4"
            emptyLabel="No footprint recorded"
          />
          <ol className="mt-2 space-y-1">
            {footprint.map((code, i) => (
              <li key={code} className="flex items-baseline gap-2 text-xs">
                <span className="w-4 shrink-0 text-right text-[10px] text-muted">
                  {i + 1}
                </span>
                <span className="flex-1 truncate">{countryName(code)}</span>
                {tickersByCountry[code] && (
                  <span className="shrink-0 text-[10px] text-accent">
                    {tickersByCountry[code].join(" ")}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {unmappable.length > 0 && (
            <div className="mt-2 text-[10px] text-muted">
              Not shaded on the map (too small at this resolution):{" "}
              {unmappable.map(countryName).join(", ")}
            </div>
          )}
        </div>

        {/* ---------------- attention origin ---------------- */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 flex items-baseline justify-between gap-2">
            <span className="text-xs font-semibold" style={{ color: "#60a5fa" }}>
              WHERE THE SEARCHES COME FROM
            </span>
            <span className="text-[10px] text-muted">Google Trends</span>
          </div>
          <GeoMap
            values={interestValues}
            accent="#60a5fa"
            emptyLabel="Awaiting first weekly geo refresh"
          />
          <ol className="mt-2 space-y-1">
            {topInterest.map((g) => (
              <li key={g.country} className="flex items-center gap-2 text-xs">
                <span className="w-28 shrink-0 truncate">{countryName(g.country)}</span>
                <span className="relative h-2 flex-1 overflow-hidden rounded-sm bg-panel2">
                  <span
                    className="absolute inset-y-0 left-0 rounded-sm"
                    style={{
                      width: `${g.interest}%`,
                      background: "#60a5fa",
                      opacity: 0.8,
                    }}
                  />
                </span>
                <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-muted">
                  {Math.round(g.interest)}
                </span>
              </li>
            ))}
            {topInterest.length === 0 && (
              <li className="text-[11px] text-muted">
                No country data yet — this refreshes weekly once the collector runs.
              </li>
            )}
          </ol>
          <div className="mt-2 text-[10px] leading-relaxed text-muted">
            Relative within this theme (top country = 100), not comparable across themes.
            Queries are in English, so this over-weights the US, UK, Canada and Australia
            regardless of where the industry actually is.
          </div>
        </div>
      </div>
    </div>
  );
}
