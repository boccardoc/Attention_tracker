"use client";

import { useMemo } from "react";
import type { ThemeData } from "../lib/types";
import { fmtPct, fmtZ } from "../lib/ui";

type Channel = "research" | "speculative";

function velSeries(t: ThemeData, ch: Channel): number[] {
  const key = ch === "research" ? "research_velocity_7d" : "speculative_velocity_7d";
  return t.history
    .map((h) => h[key])
    .filter((v): v is number => v !== null)
    .slice(-14);
}

function latestVel(t: ThemeData, ch: Channel): number | null {
  const key = ch === "research" ? "research_velocity_7d" : "speculative_velocity_7d";
  return t.latest?.[key] ?? null;
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return <span className="text-muted">—</span>;
  const w = 72;
  const h = 20;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

function MoversTable({
  themes,
  channel,
  title,
  color,
  onSelect,
}: {
  themes: ThemeData[];
  channel: Channel;
  title: string;
  color: string;
  onSelect: (id: string) => void;
}) {
  const ranked = useMemo(() => {
    return themes
      .filter((t) => latestVel(t, channel) !== null)
      .sort((a, b) => (latestVel(b, channel) ?? 0) - (latestVel(a, channel) ?? 0))
      .slice(0, 10);
  }, [themes, channel]);

  return (
    <div className="rounded-lg border border-edge bg-panel">
      <div className="border-b border-edge px-3 py-2 text-xs font-semibold" style={{ color }}>
        {title}
      </div>
      {ranked.length === 0 ? (
        <div className="p-3 text-xs text-muted">
          No velocity yet (channel warming up).
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-muted">
            <tr className="text-left">
              <th className="px-3 py-1.5 font-normal">theme</th>
              <th className="px-2 py-1.5 text-right font-normal">res z</th>
              <th className="px-2 py-1.5 text-right font-normal">spec z</th>
              <th className="px-2 py-1.5 font-normal">vel 14d</th>
              <th className="px-2 py-1.5 text-right font-normal">ETF 7d</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((t) => {
              const etf = t.quotes.find((q) => q.ticker === t.basket.etf);
              return (
                <tr
                  key={t.id}
                  onClick={() => onSelect(t.id)}
                  className="cursor-pointer border-t border-edge/60 hover:bg-panel2"
                >
                  <td className="px-3 py-1.5">{t.name}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {fmtZ(t.latest?.research_z)}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {fmtZ(t.latest?.speculative_z)}
                  </td>
                  <td className="px-2 py-1.5">
                    <Sparkline data={velSeries(t, channel)} color={color} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <div className="tabular-nums">{t.basket.etf ?? "—"}</div>
                    <div
                      className={
                        (etf?.change7d ?? 0) >= 0 ? "text-early" : "text-froth"
                      }
                    >
                      {fmtPct(etf?.change7d)}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Movers({
  themes,
  onSelect,
}: {
  themes: ThemeData[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <MoversTable
        themes={themes}
        channel="research"
        title="TOP 10 · RESEARCH VELOCITY (7d)"
        color="#60a5fa"
        onSelect={onSelect}
      />
      <MoversTable
        themes={themes}
        channel="speculative"
        title="TOP 10 · SPECULATIVE VELOCITY (7d)"
        color="#f43f5e"
        onSelect={onSelect}
      />
    </div>
  );
}
