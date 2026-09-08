"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ThemeData } from "../lib/types";
import {
  CATEGORY_COLORS,
  categoryColor,
  fmtShare,
  fmtZ,
  quadrant,
  sentimentColor,
  sentimentLabel,
} from "../lib/ui";

const TRAIL_DAYS = 14;

interface Pt {
  id: string;
  name: string;
  category: string;
  color: string;
  x: number; // speculative_z
  y: number; // research_z
  r: number; // radius from |combined velocity|
  ring: string; // outline colour = Reddit tone (separate channel, never blended into x/y)
  tone: string;
  share: number | null;
}

export default function RotationMap({
  themes,
  onSelect,
}: {
  themes: ThemeData[];
  onSelect: (id: string) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  const { points, warming, domain } = useMemo(() => {
    const points: Pt[] = [];
    const warming: ThemeData[] = [];
    for (const t of themes) {
      const l = t.latest;
      if (!l || l.research_z === null) continue;
      if (l.speculative_z === null) {
        warming.push(t); // research ready, speculative still ramping (<30d Reddit)
        continue;
      }
      const vel =
        Math.abs(l.research_velocity_7d ?? 0) +
        Math.abs(l.speculative_velocity_7d ?? 0);
      points.push({
        id: t.id,
        name: t.name,
        category: t.category,
        color: categoryColor(t.category),
        x: l.speculative_z,
        y: l.research_z,
        r: 4 + Math.min(14, vel * 4), // size by 7d combined velocity (abs)
        ring: sentimentColor(l.sentiment_z),
        tone: sentimentLabel(l.sentiment_z),
        share: l.share_pct,
      });
    }
    let maxAbs = 2;
    for (const p of points) maxAbs = Math.max(maxAbs, Math.abs(p.x), Math.abs(p.y));
    const d = Math.ceil((maxAbs + 0.5) * 10) / 10;
    return { points, warming, domain: [-d, d] as [number, number] };
  }, [themes]);

  // 14-day trail for the hovered point (direction of travel).
  const trail = useMemo(() => {
    if (!hovered) return [];
    const t = themes.find((x) => x.id === hovered);
    if (!t) return [];
    return t.history
      .filter((h) => h.research_z !== null && h.speculative_z !== null)
      .slice(-TRAIL_DAYS)
      .map((h) => ({ x: h.speculative_z as number, y: h.research_z as number }));
  }, [hovered, themes]);

  const dot = (props: any) => {
    const { cx, cy, payload } = props;
    const active = hovered === payload.id;
    return (
      <circle
        cx={cx}
        cy={cy}
        r={payload.r}
        fill={payload.color}
        fillOpacity={active ? 0.95 : 0.7}
        // Ring encodes Reddit tone. It is an outline, not a position, precisely so
        // sentiment never contaminates the two attention axes.
        stroke={active ? "#fff" : payload.ring}
        strokeWidth={active ? 2 : 1.5}
        style={{ cursor: "pointer" }}
        onClick={() => onSelect(payload.id)}
        onMouseEnter={() => setHovered(payload.id)}
        onMouseLeave={() => setHovered(null)}
      />
    );
  };

  return (
    <div>
      <div className="grid gap-3 lg:grid-cols-[1fr_180px]">
        <div className="rounded-lg border border-edge bg-panel p-2">
          <div className="h-[560px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 8 }}>
                {/* EARLY ROTATION quadrant highlight (research>0, speculative<0) */}
                <ReferenceArea
                  x1={domain[0]}
                  x2={0}
                  y1={0}
                  y2={domain[1]}
                  fill="#22c55e"
                  fillOpacity={0.07}
                />
                <CartesianGrid stroke="#1c2230" />
                <XAxis
                  type="number"
                  dataKey="x"
                  domain={domain}
                  tick={{ fill: "#8b93a7", fontSize: 11 }}
                  stroke="#262c38"
                  label={{
                    value: "speculative z  (Reddit · fast money) →",
                    position: "bottom",
                    fill: "#8b93a7",
                    fontSize: 11,
                  }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  domain={domain}
                  tick={{ fill: "#8b93a7", fontSize: 11 }}
                  stroke="#262c38"
                  label={{
                    value: "research z  (Wiki+Trends · slow money) →",
                    angle: -90,
                    position: "left",
                    fill: "#8b93a7",
                    fontSize: 11,
                  }}
                />
                <ReferenceLine x={0} stroke="#39414f" />
                <ReferenceLine y={0} stroke="#39414f" />
                <Tooltip
                  cursor={{ stroke: "#39414f" }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as Pt;
                    return (
                      <div className="rounded border border-edge bg-ink/95 p-2 text-xs">
                        <div className="font-semibold" style={{ color: p.color }}>
                          {p.name}
                        </div>
                        <div className="text-muted">{p.category}</div>
                        <div className="mt-1">
                          research z {fmtZ(p.y)} · spec z {fmtZ(p.x)}
                        </div>
                        <div className="text-muted">
                          share {fmtShare(p.share)} · tone{" "}
                          <span style={{ color: p.ring }}>{p.tone}</span>
                        </div>
                        <div className="text-accent">{quadrant(p.y, p.x)}</div>
                      </div>
                    );
                  }}
                />
                {trail.length > 1 && (
                  <Scatter
                    data={trail}
                    line={{ stroke: "#5eead4", strokeOpacity: 0.5 }}
                    shape={() => <></>}
                    isAnimationActive={false}
                  />
                )}
                <Scatter
                  data={points}
                  shape={dot}
                  isAnimationActive={false}
                />
                {/* Quadrant labels */}
                <text x="22%" y="8%" fill="#22c55e" fontSize={12} fontWeight={600}>
                  EARLY ROTATION
                </text>
                <text x="72%" y="8%" fill="#8b93a7" fontSize={12}>
                  CROWDED CONSENSUS
                </text>
                <text x="72%" y="95%" fill="#f43f5e" fontSize={12}>
                  FROTH / MEME
                </text>
                <text x="22%" y="95%" fill="#8b93a7" fontSize={12}>
                  DORMANT
                </text>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>

        <aside className="space-y-3">
          <div className="rounded-lg border border-edge bg-panel p-3">
            <div className="mb-2 text-xs font-semibold text-muted">CATEGORIES</div>
            <div className="space-y-1">
              {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
                <div key={cat} className="flex items-center gap-2 text-xs">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: color }}
                  />
                  <span className="text-muted">{cat}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 border-t border-edge pt-2 text-[11px] text-muted">
              point size = |7d combined velocity|. hover a point for its 14-day trail;
              click to open detail.
            </div>
            <div className="mt-2 border-t border-edge pt-2">
              <div className="mb-1 text-[11px] font-semibold text-muted">
                RING = REDDIT TONE
              </div>
              <div className="space-y-1">
                {[
                  ["#22c55e", "positive"],
                  ["#8b93a7", "mixed / no read"],
                  ["#f43f5e", "negative"],
                ].map(([c, label]) => (
                  <div key={label} className="flex items-center gap-2 text-[11px]">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full border-2"
                      style={{ borderColor: c, background: "transparent" }}
                    />
                    <span className="text-muted">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {warming.length > 0 && (
            <div className="rounded-lg border border-edge bg-panel p-3">
              <div className="mb-1 text-xs font-semibold text-accent">
                WARMING UP ({warming.length})
              </div>
              <div className="text-[11px] text-muted">
                speculative channel &lt;30d of Reddit history — research only:
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {warming.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => onSelect(t.id)}
                    className="rounded bg-panel2 px-1.5 py-0.5 text-[11px] text-muted hover:text-white"
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
