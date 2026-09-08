"use client";

import { useMemo, useState } from "react";
import type { Institutions as InstitutionsData, ThemeData } from "../lib/types";

/**
 * What the big managers hold, and what the banks are saying.
 *
 * Two signals that are NOT the same thing and are never merged:
 *   13F holdings  — committed capital, quarterly, filed up to 45 days after quarter end
 *   analyst calls — published opinion, continuous, no capital behind it
 *
 * The ranking is by quarter-over-quarter CHANGE, not by holdings. Index managers own
 * nearly everything in proportion to market cap, so ranking by absolute dollars would
 * just re-rank the themes by size. For the same reason passive money is shown apart from
 * active: BlackRock adding to a theme is usually fund flows, not a view.
 */
export default function Institutions({
  data,
  themes,
  onSelect,
}: {
  data: InstitutionsData;
  themes: ThemeData[];
  onSelect: (id: string) => void;
}) {
  const [styleFilter, setStyleFilter] = useState<"active" | "all">("active");

  const nameById = useMemo(
    () => Object.fromEntries(themes.map((t) => [t.id, t.name])),
    [themes],
  );

  const ranked = useMemo(() => {
    const rows = data.themes.map((t) => {
      const relevant =
        styleFilter === "active"
          ? t.byStyle.filter((s) => s.style === "active")
          : t.byStyle;
      return {
        ...t,
        shownDelta: relevant.reduce((s, x) => s + x.delta, 0),
        shownValue: relevant.reduce((s, x) => s + x.value, 0),
      };
    });
    return rows.sort((a, b) => b.shownDelta - a.shownDelta);
  }, [data.themes, styleFilter]);

  const analysts = useMemo(
    () => [...data.analysts].sort((a, b) => b.net - a.net),
    [data.analysts],
  );

  const maxAbs = Math.max(...ranked.map((r) => Math.abs(r.shownDelta)), 1);

  if (!data.themes.length && !data.analysts.length) {
    return (
      <div className="rounded-lg border border-edge bg-panel p-6 text-sm text-muted">
        No institutional data yet — 13F holdings appear after the collector runs.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* staleness is stated up front, not buried */}
      <div className="rounded-lg border border-accent/30 bg-panel2 p-3 text-xs">
        <span className="text-accent">Positions as of {data.quarter || "—"}</span>
        <span className="text-muted">
          {" "}· 13F filings are due up to 45 days after quarter end, so this is between 45
          and 135 days old. It covers long US-listed equity only — no shorts, bonds,
          derivatives or foreign listings.
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* ---------------- 13F accumulation ---------------- */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 flex items-baseline justify-between gap-2">
            <span className="text-xs font-semibold text-accent">
              WHERE THE MONEY MOVED
            </span>
            <div className="flex gap-1">
              {(["active", "all"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setStyleFilter(s)}
                  className={`rounded px-2 py-0.5 text-[10px] ${
                    styleFilter === s
                      ? "bg-panel2 text-accent"
                      : "text-muted hover:text-white"
                  }`}
                >
                  {s === "active" ? "active only" : "all managers"}
                </button>
              ))}
            </div>
          </div>
          <div className="mb-3 text-[11px] text-muted">
            Change in holdings from {data.prevQuarter || "—"} to {data.quarter || "—"}.
            {styleFilter === "active"
              ? " Active managers only — every position is an actual decision."
              : " Including index funds, whose moves are mostly fund flows, not views."}
          </div>

          <div className="space-y-1">
            {ranked.slice(0, 12).map((r) => {
              const pos = r.shownDelta >= 0;
              return (
                <button
                  key={r.theme_id}
                  onClick={() => onSelect(r.theme_id)}
                  className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-panel2"
                >
                  <span className="w-36 shrink-0 truncate text-xs">
                    {nameById[r.theme_id] ?? r.theme_id}
                  </span>
                  <span className="relative h-3 flex-1 overflow-hidden rounded-sm bg-panel2">
                    <span
                      className="absolute inset-y-0 rounded-sm"
                      style={{
                        left: pos ? "50%" : undefined,
                        right: pos ? undefined : "50%",
                        width: `${(Math.abs(r.shownDelta) / maxAbs) * 50}%`,
                        background: pos ? "#22c55e" : "#f43f5e",
                        opacity: 0.85,
                      }}
                    />
                    <span className="absolute inset-y-0 left-1/2 w-px bg-edge" />
                  </span>
                  <span
                    className={`w-16 shrink-0 text-right text-xs tabular-nums ${
                      pos ? "text-early" : "text-froth"
                    }`}
                  >
                    {fmtDelta(r.shownDelta)}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-3 border-t border-edge pt-2 text-[10px] leading-relaxed text-muted">
            Ranked by <em>change</em>, never by size: index managers hold nearly every name
            in proportion to market cap, so a ranking by holdings would just rank themes by
            how big they are.
          </div>
        </div>

        {/* ---------------- analyst actions ---------------- */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 text-xs font-semibold" style={{ color: "#60a5fa" }}>
            WHAT THE BANKS ARE SAYING
          </div>
          <div className="mb-3 text-[11px] text-muted">
            Upgrades minus downgrades across each basket, last 90 days. Continuous, unlike
            13F — but this is published opinion, not committed capital.
          </div>

          <div className="space-y-1">
            {analysts.slice(0, 12).map((a) => (
              <button
                key={a.theme_id}
                onClick={() => onSelect(a.theme_id)}
                className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-panel2"
                title={a.recent
                  .map((r) => `${r.date} ${r.firm}: ${r.action} ${r.ticker}`)
                  .join("\n")}
              >
                <span className="w-36 shrink-0 truncate text-xs">
                  {nameById[a.theme_id] ?? a.theme_id}
                </span>
                <span className="flex-1 truncate text-[10px] text-muted">
                  {[...new Set(a.recent.map((r) => r.firm))].slice(0, 3).join(", ")}
                </span>
                <span className="shrink-0 text-[10px] tabular-nums text-early">
                  +{a.upgrades}
                </span>
                <span className="shrink-0 text-[10px] tabular-nums text-froth">
                  −{a.downgrades}
                </span>
                <span
                  className={`w-8 shrink-0 text-right text-xs tabular-nums ${
                    a.net >= 0 ? "text-early" : "text-froth"
                  }`}
                >
                  {a.net >= 0 ? "+" : ""}
                  {a.net}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* style split for the top movers, so passive is never mistaken for conviction */}
      <div className="rounded-lg border border-edge bg-panel p-3">
        <div className="mb-1 text-xs font-semibold text-muted">
          PASSIVE VS ACTIVE VS BANK
        </div>
        <div className="mb-2 text-[11px] text-muted">
          BlackRock owning a theme is index replication, not a view. Bank 13Fs mix client
          assets and market-making inventory. Only the active column reflects deliberate
          stock selection.
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted">
              <tr className="text-left">
                <th className="px-2 py-1.5 font-normal">theme</th>
                <th className="px-2 py-1.5 text-right font-normal">active Δ</th>
                <th className="px-2 py-1.5 text-right font-normal">passive Δ</th>
                <th className="px-2 py-1.5 text-right font-normal">bank Δ</th>
                <th className="px-2 py-1.5 text-right font-normal">held</th>
              </tr>
            </thead>
            <tbody>
              {ranked.slice(0, 10).map((r) => (
                <tr
                  key={r.theme_id}
                  onClick={() => onSelect(r.theme_id)}
                  className="cursor-pointer border-t border-edge/60 hover:bg-panel2"
                >
                  <td className="px-2 py-1.5">{nameById[r.theme_id] ?? r.theme_id}</td>
                  {(["active", "passive", "bank"] as const).map((s) => {
                    const d = r.byStyle.find((x) => x.style === s)?.delta ?? 0;
                    return (
                      <td
                        key={s}
                        className={`px-2 py-1.5 text-right tabular-nums ${
                          d > 0 ? "text-early" : d < 0 ? "text-froth" : "text-muted"
                        }`}
                      >
                        {d ? fmtDelta(d) : "—"}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5 text-right tabular-nums text-muted">
                    {fmtUsd(r.total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function fmtUsd(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function fmtDelta(v: number): string {
  return `${v >= 0 ? "+" : "−"}${fmtUsd(Math.abs(v)).replace("$", "$")}`;
}
