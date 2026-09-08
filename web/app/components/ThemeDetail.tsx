"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ThemeData } from "../lib/types";
import {
  divergenceCallout,
  fmtPct,
  fmtShare,
  fmtZ,
  sentimentLabel,
} from "../lib/ui";

export default function ThemeDetail({
  themes,
  selected,
  onSelect,
}: {
  themes: ThemeData[];
  selected: ThemeData | null;
  onSelect: (id: string) => void;
}) {
  const t = selected ?? themes[0] ?? null;

  const merged = useMemo(() => {
    if (!t) return [];
    const priceByDate = new Map(t.etfPrices.map((p) => [p.date, p.close]));
    const firstClose = t.etfPrices.length ? t.etfPrices[0].close : null;
    return t.history.map((h) => {
      const close = priceByDate.get(h.date);
      const priceIdx =
        close != null && firstClose ? (close / firstClose) * 100 : null;
      return {
        date: h.date,
        research_z: h.research_z,
        speculative_z: h.speculative_z,
        sentiment_z: h.sentiment_z,
        priceIdx,
      };
    });
  }, [t]);

  if (!t) return <div className="text-sm text-muted">No themes.</div>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={t.id}
          onChange={(e) => onSelect(e.target.value)}
          className="rounded border border-edge bg-panel px-2 py-1 text-sm"
        >
          {themes.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted">{t.category}</span>
        {t.basket.etf && (
          <span className="rounded bg-panel2 px-2 py-0.5 text-xs text-accent">
            {t.basket.etf}
          </span>
        )}
        <span className="text-xs text-muted">added {t.date_added}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Stat
          label="share of attention"
          value={fmtShare(t.latest?.share_pct)}
          hint="of all 40 themes today"
        />
        <Stat label="research z" value={fmtZ(t.latest?.research_z)} />
        <Stat
          label="speculative z"
          value={fmtZ(t.latest?.speculative_z)}
          hint={t.latest?.speculative_z == null ? "warming up" : undefined}
        />
        <Stat
          label="reddit tone"
          value={sentimentLabel(t.latest?.sentiment_z)}
          hint={
            t.latest?.sentiment_z == null
              ? "too few posts"
              : `z ${fmtZ(t.latest.sentiment_z)} · low confidence`
          }
        />
      </div>

      <div className="rounded-lg border border-froth/30 bg-panel2 p-3 text-sm">
        <span className="text-muted">divergence read · </span>
        {divergenceCallout(t)}
      </div>

      <div className="rounded-lg border border-edge bg-panel p-2">
        <div className="h-[360px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={merged} margin={{ top: 12, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#1c2230" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#8b93a7", fontSize: 10 }}
                stroke="#262c38"
                minTickGap={48}
              />
              <YAxis
                yAxisId="z"
                tick={{ fill: "#8b93a7", fontSize: 10 }}
                stroke="#262c38"
                width={32}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                tick={{ fill: "#8b93a7", fontSize: 10 }}
                stroke="#262c38"
                width={36}
              />
              <ReferenceLine yAxisId="z" y={0} stroke="#39414f" />
              <Tooltip
                contentStyle={{
                  background: "#0a0c10",
                  border: "1px solid #262c38",
                  fontSize: 12,
                }}
              />
              <Line
                yAxisId="z"
                type="monotone"
                dataKey="research_z"
                name="research z"
                stroke="#60a5fa"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
              <Line
                yAxisId="z"
                type="monotone"
                dataKey="speculative_z"
                name="speculative z"
                stroke="#f43f5e"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
              {/* Tone is drawn thinner and dashed to read as the low-confidence
                  overlay it is, not as a peer of the two attention channels. */}
              <Line
                yAxisId="z"
                type="monotone"
                dataKey="sentiment_z"
                name="sentiment z (Reddit tone)"
                stroke="#a78bfa"
                strokeDasharray="5 3"
                dot={false}
                strokeWidth={1.5}
                connectNulls
              />
              {t.basket.etf && (
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="priceIdx"
                  name={`${t.basket.etf} (idx=100)`}
                  stroke="#8b93a7"
                  strokeDasharray="4 3"
                  dot={false}
                  strokeWidth={1.5}
                  connectNulls
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-4 px-2 pb-1 text-[11px] text-muted">
          <Legend color="#60a5fa" label="research z" />
          <Legend color="#f43f5e" label="speculative z" />
          <Legend color="#a78bfa" label="sentiment z (Reddit tone, low confidence)" />
          {t.basket.etf && <Legend color="#8b93a7" label={`${t.basket.etf} price (idx)`} />}
        </div>
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold text-muted">BASKET</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
          {t.quotes.map((q) => {
            const isEtf = q.ticker === t.basket.etf;
            return (
              <div
                key={q.ticker}
                className={`rounded-lg border bg-panel p-3 ${
                  isEtf ? "border-accent/40" : "border-edge"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{q.ticker}</span>
                  {isEtf && <span className="text-[10px] text-accent">ETF</span>}
                </div>
                <div className="mt-1 text-xs text-muted">
                  {q.latest != null ? `$${q.latest.toFixed(2)}` : "—"}
                </div>
                <div
                  className={`text-xs ${
                    (q.change7d ?? 0) >= 0 ? "text-early" : "text-froth"
                  }`}
                >
                  {fmtPct(q.change7d)} 7d
                </div>
              </div>
            );
          })}
        </div>
      </div>
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
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-accent">{hint}</div>}
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
