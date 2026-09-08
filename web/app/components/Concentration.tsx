"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ConcentrationPoint, ThemeData } from "../lib/types";
import {
  BLOCK_COLORS,
  categoryColor,
  fmtShare,
  fmtZ,
  macroBlock,
  sentimentColor,
  sentimentLabel,
} from "../lib/ui";

/**
 * Answers "where is attention concentrated right now" using absolute share of all
 * themes' attention -- deliberately NOT z-scores, which normalise each theme against
 * its own history and so cannot rank themes against each other.
 */
export default function Concentration({
  themes,
  concentration,
  onSelect,
}: {
  themes: ThemeData[];
  concentration: ConcentrationPoint[];
  onSelect: (id: string) => void;
}) {
  const ranked = useMemo(
    () =>
      themes
        .filter((t) => t.latest?.share_pct != null)
        .sort((a, b) => (b.latest!.share_pct ?? 0) - (a.latest!.share_pct ?? 0)),
    [themes],
  );

  const blocks = useMemo(() => {
    const acc = new Map<string, { share: number; themes: number }>();
    for (const t of ranked) {
      const b = macroBlock(t.category);
      const cur = acc.get(b) ?? { share: 0, themes: 0 };
      cur.share += t.latest!.share_pct ?? 0;
      cur.themes += 1;
      acc.set(b, cur);
    }
    return [...acc.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.share - a.share);
  }, [ranked]);

  const latest = concentration.length
    ? concentration[concentration.length - 1]
    : null;
  const evenShare = ranked.length ? 1 / ranked.length : 0;
  const hhiRatio = latest?.hhi ? latest.hhi / evenShare : null;

  const breadth = useMemo(
    () =>
      concentration.map((c) => ({
        date: c.date,
        early: c.breadth_early ?? 0,
        crowded: c.breadth_crowded ?? 0,
        froth: c.breadth_froth ?? 0,
        dormant: c.breadth_dormant ?? 0,
      })),
    [concentration],
  );

  if (!ranked.length) {
    return (
      <div className="rounded-lg border border-edge bg-panel p-6 text-sm text-muted">
        No share data yet — run the collector to populate concentration.
      </div>
    );
  }

  const maxShare = ranked[0].latest!.share_pct ?? 1;

  return (
    <div className="space-y-4">
      {/* headline numbers */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="top 5 hold"
          value={fmtShare(latest?.top5_share)}
          hint={`of all tracked attention · ${ranked.length} themes`}
        />
        <Stat
          label="concentration (HHI)"
          value={latest?.hhi != null ? latest.hhi.toFixed(4) : "—"}
          hint={
            hhiRatio
              ? `${hhiRatio.toFixed(2)}× an even split — ${
                  hhiRatio > 1.15 ? "narrowing" : "broadly spread"
                }`
              : "—"
          }
        />
        <Stat
          label="most concentrated"
          value={ranked[0].name}
          hint={`${fmtShare(ranked[0].latest!.share_pct)} of all attention`}
        />
      </div>

      {/* the actual answer: ranked share of attention */}
      <div className="rounded-lg border border-edge bg-panel p-3">
        <div className="mb-1 text-xs font-semibold text-accent">
          WHERE ATTENTION IS CONCENTRATED
        </div>
        <div className="mb-3 text-[11px] text-muted">
          Each theme&apos;s share of all tracked attention today. Absolute, so themes are
          comparable with each other — unlike z-scores, which only compare a theme with
          its own past.
        </div>
        <div className="space-y-1">
          {ranked.slice(0, 20).map((t) => {
            const share = t.latest!.share_pct ?? 0;
            return (
              <button
                key={t.id}
                onClick={() => onSelect(t.id)}
                className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-panel2"
              >
                <span className="w-40 shrink-0 truncate text-xs">{t.name}</span>
                <span className="relative h-3.5 flex-1 overflow-hidden rounded-sm bg-panel2">
                  <span
                    className="absolute inset-y-0 left-0 rounded-sm"
                    style={{
                      width: `${(share / maxShare) * 100}%`,
                      background: categoryColor(t.category),
                      opacity: 0.85,
                    }}
                  />
                </span>
                <span className="w-14 shrink-0 text-right text-xs tabular-nums">
                  {fmtShare(share)}
                </span>
                <span
                  className="w-16 shrink-0 text-right text-[10px]"
                  style={{ color: sentimentColor(t.latest?.sentiment_z) }}
                  title="Reddit tone (VADER) — low-confidence overlay"
                >
                  {sentimentLabel(t.latest?.sentiment_z)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* macro block rollup */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 text-xs font-semibold text-muted">BY MACRO BLOCK</div>
          <div className="mb-3 text-[11px] text-muted">
            The 13 categories are too unevenly sized to average, so these coarser blocks
            (3–9 themes each) carry the rollup.
          </div>
          <div className="space-y-1.5">
            {blocks.map((b) => (
              <div key={b.name} className="flex items-center gap-2">
                <span className="w-44 shrink-0 truncate text-xs">{b.name}</span>
                <span className="relative h-3.5 flex-1 overflow-hidden rounded-sm bg-panel2">
                  <span
                    className="absolute inset-y-0 left-0 rounded-sm"
                    style={{
                      width: `${(b.share / (blocks[0]?.share || 1)) * 100}%`,
                      background: BLOCK_COLORS[b.name] ?? "#94a3b8",
                      opacity: 0.85,
                    }}
                  />
                </span>
                <span className="w-14 shrink-0 text-right text-xs tabular-nums">
                  {fmtShare(b.share)}
                </span>
                <span className="w-8 shrink-0 text-right text-[10px] text-muted">
                  n={b.themes}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* is attention narrowing or broadening */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-1 text-xs font-semibold text-muted">
            NARROWING OR BROADENING
          </div>
          <div className="mb-2 text-[11px] text-muted">
            Top-5 share over 180 days. Rising = attention crowding into fewer themes.
          </div>
          <div className="h-[180px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={concentration} margin={{ top: 6, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="#1c2230" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#8b93a7", fontSize: 10 }}
                  stroke="#262c38"
                  minTickGap={54}
                />
                <YAxis
                  tick={{ fill: "#8b93a7", fontSize: 10 }}
                  stroke="#262c38"
                  width={44}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                />
                <Tooltip
                  contentStyle={{
                    background: "#0a0c10",
                    border: "1px solid #262c38",
                    fontSize: 12,
                  }}
                  formatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                />
                <Line
                  type="monotone"
                  dataKey="top5_share"
                  name="top 5 share"
                  stroke="#5eead4"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* regime breadth */}
      <div className="rounded-lg border border-edge bg-panel p-3">
        <div className="mb-1 text-xs font-semibold text-muted">
          REGIME — THEMES PER QUADRANT OVER TIME
        </div>
        <div className="mb-2 text-[11px] text-muted">
          A market-wide read: when EARLY ROTATION swells, fresh themes are being
          researched ahead of the crowd; when FROTH dominates, attention is late-stage.
        </div>
        <div className="h-[200px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={breadth} margin={{ top: 6, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#1c2230" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#8b93a7", fontSize: 10 }}
                stroke="#262c38"
                minTickGap={54}
              />
              <YAxis tick={{ fill: "#8b93a7", fontSize: 10 }} stroke="#262c38" width={30} />
              <Tooltip
                contentStyle={{
                  background: "#0a0c10",
                  border: "1px solid #262c38",
                  fontSize: 12,
                }}
              />
              <Area type="monotone" dataKey="early" stackId="1" name="early rotation" stroke="#22c55e" fill="#22c55e" fillOpacity={0.5} />
              <Area type="monotone" dataKey="crowded" stackId="1" name="crowded" stroke="#60a5fa" fill="#60a5fa" fillOpacity={0.4} />
              <Area type="monotone" dataKey="froth" stackId="1" name="froth" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.4} />
              <Area type="monotone" dataKey="dormant" stackId="1" name="dormant" stroke="#64748b" fill="#64748b" fillOpacity={0.3} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-3 pt-2 text-[11px] text-muted">
          <Legend color="#22c55e" label="early rotation" />
          <Legend color="#60a5fa" label="crowded consensus" />
          <Legend color="#f43f5e" label="froth / meme" />
          <Legend color="#64748b" label="dormant" />
        </div>
      </div>

      <p className="text-[11px] leading-relaxed text-muted">
        Share measures <em>attention</em>, not industry fundamentals — it shows where
        interest is pooling, which tends to peak alongside price rather than lead it.
        Sentiment is a low-confidence VADER read of Reddit tone only; the research
        channel has no text to score.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-2 w-3" style={{ background: color }} />
      {label}
    </span>
  );
}
