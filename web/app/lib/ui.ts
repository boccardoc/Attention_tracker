import type { ThemeData } from "./types";

// Stable category -> color map for the scatter and legends.
export const CATEGORY_COLORS: Record<string, string> = {
  Technology: "#60a5fa",
  Energy: "#f59e0b",
  Materials: "#a3a3a3",
  Consumer: "#f472b6",
  Industrials: "#34d399",
  Healthcare: "#22d3ee",
  Financials: "#818cf8",
  "Real Estate": "#fb923c",
  Crypto: "#fbbf24",
  International: "#c084fc",
  Communications: "#f87171",
  Infrastructure: "#2dd4bf",
  Macro: "#94a3b8",
};

export function categoryColor(category: string): string {
  return CATEGORY_COLORS[category] ?? "#94a3b8";
}

// The 13 categories are too unevenly sized to average (Real Estate, Infrastructure and
// Macro hold a single theme each, so their "average" is just that theme). These coarser
// blocks hold 3-9 themes apiece and are what the macro rollup aggregates over; the
// categories above are still used for point colour.
export const MACRO_BLOCKS: Record<string, string> = {
  Energy: "Energy & Power",
  Infrastructure: "Energy & Power",
  Technology: "Technology & AI",
  Communications: "Technology & AI",
  Materials: "Materials & Industrials",
  Industrials: "Materials & Industrials",
  Healthcare: "Healthcare",
  Financials: "Financials & Crypto",
  Crypto: "Financials & Crypto",
  "Real Estate": "Financials & Crypto",
  Consumer: "Consumer & Global",
  International: "Consumer & Global",
  Macro: "Consumer & Global",
};

export const BLOCK_COLORS: Record<string, string> = {
  "Energy & Power": "#f59e0b",
  "Technology & AI": "#60a5fa",
  "Materials & Industrials": "#34d399",
  Healthcare: "#22d3ee",
  "Financials & Crypto": "#818cf8",
  "Consumer & Global": "#f472b6",
};

export function macroBlock(category: string): string {
  return MACRO_BLOCKS[category] ?? "Consumer & Global";
}

/** Sentiment is a low-confidence overlay, so it reads as a word, not a number. */
export function sentimentLabel(z: number | null | undefined): string {
  if (z === null || z === undefined) return "no read";
  if (z >= 1) return "positive";
  if (z <= -1) return "negative";
  return "mixed";
}

export function sentimentColor(z: number | null | undefined): string {
  if (z === null || z === undefined) return "#8b93a7";
  if (z >= 1) return "#22c55e";
  if (z <= -1) return "#f43f5e";
  return "#8b93a7";
}

export function fmtShare(share: number | null | undefined): string {
  return share === null || share === undefined ? "—" : `${(share * 100).toFixed(2)}%`;
}

export type Quadrant = "EARLY ROTATION" | "CROWDED CONSENSUS" | "FROTH / MEME" | "DORMANT";

export function quadrant(researchZ: number, speculativeZ: number): Quadrant {
  if (researchZ >= 0 && speculativeZ < 0) return "EARLY ROTATION";
  if (researchZ >= 0 && speculativeZ >= 0) return "CROWDED CONSENSUS";
  if (researchZ < 0 && speculativeZ >= 0) return "FROTH / MEME";
  return "DORMANT";
}

export function fmtZ(z: number | null | undefined): string {
  return z === null || z === undefined ? "—" : z.toFixed(2);
}

export function fmtPct(p: number | null | undefined): string {
  if (p === null || p === undefined) return "—";
  const sign = p >= 0 ? "+" : "";
  return `${sign}${(p * 100).toFixed(1)}%`;
}

/** Plain-language divergence read from latest z + 7d velocities + ETF 7d price move. */
export function divergenceCallout(t: ThemeData): string {
  const l = t.latest;
  if (!l || l.research_z === null) return "Not enough history yet to read divergence.";
  const etf = t.quotes.find((q) => q.ticker === t.basket.etf);
  const priceMove = etf?.change7d ?? null;
  const researchRising = (l.research_velocity_7d ?? 0) > 0.1;
  const researchFalling = (l.research_velocity_7d ?? 0) < -0.1;
  const priceUp = priceMove !== null && priceMove > 0.01;
  const priceFlatOrDown = priceMove !== null && priceMove <= 0.01;

  if (researchRising && priceFlatOrDown)
    return "Research attention rising while price is flat — early-stage setup.";
  if (priceUp && researchFalling)
    return "Price rising while attention falls — exhaustion risk.";
  if (l.speculative_z === null)
    return "Speculative channel still warming up (<30 days of Reddit history).";
  if ((l.speculative_z ?? 0) > 1.5 && (l.research_z ?? 0) < 0.5)
    return "Speculative attention well above research — froth/meme dynamics.";
  if ((l.research_z ?? 0) > 1 && (l.speculative_z ?? 0) < 0)
    return "Research leads speculation — institutional interest ahead of the crowd.";
  return "No strong divergence right now — channels broadly aligned.";
}
