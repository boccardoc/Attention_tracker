import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import type {
  AnalystAction,
  AnalystTheme,
  Basket,
  BasketQuote,
  ConcentrationPoint,
  GeoInterest,
  InstitutionalTheme,
  Institutions,
  StyleHolding,
  HistoryPoint,
  PricePoint,
  ScoresResponse,
  ThemeData,
  ThemeGeo,
} from "./types";

const HISTORY_DAYS = 180;

interface RawTheme {
  id: string;
  name: string;
  category: string;
  basket: Basket;
  date_added: string;
  geo: ThemeGeo;
}

/** Resolve the shared SQLite path the same way the Python collector does. */
function dbPath(): string {
  if (process.env.ATTENTION_DB) return path.resolve(process.env.ATTENTION_DB);
  // web/ runs from its own cwd in `next dev`; the db lives at <repo>/data.
  return path.resolve(process.cwd(), "..", "data", "attention.db");
}

/** Taxonomy is the source of theme metadata (name/category/basket) — not mock data. */
function loadTaxonomy(): RawTheme[] {
  const p = path.resolve(process.cwd(), "..", "collector", "taxonomy.json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function openDb(): Database.Database {
  const p = dbPath();
  if (!fs.existsSync(p)) {
    throw new Error(
      `attention.db not found at ${p}. Run the collector (or collector/seed_demo.py) first.`,
    );
  }
  // readonly: the collector owns writes; the web app only reads.
  return new Database(p, { readonly: true, fileMustExist: true });
}

function pct7d(series: PricePoint[]): number | null {
  if (series.length === 0) return null;
  const latest = series[series.length - 1].close;
  // find the close ~7 calendar days before the latest date
  const latestDate = new Date(series[series.length - 1].date);
  const target = new Date(latestDate);
  target.setDate(target.getDate() - 7);
  let prior: number | null = null;
  for (let i = series.length - 1; i >= 0; i--) {
    if (new Date(series[i].date) <= target) {
      prior = series[i].close;
      break;
    }
  }
  if (prior === null || prior === 0) return null;
  return (latest - prior) / prior;
}

export function getScores(): ScoresResponse {
  const db = openDb();
  try {
    const themes = loadTaxonomy();

    const asOfRow = db
      .prepare("SELECT MAX(date) AS d FROM scores")
      .get() as { d: string | null };
    const asOf = asOfRow?.d ?? null;

    const historyStmt = db.prepare(
      `SELECT date, research_z, speculative_z, sentiment_z,
              research_velocity_7d, speculative_velocity_7d, sentiment_velocity_7d,
              share_pct
       FROM scores WHERE theme_id = ?
       ORDER BY date DESC LIMIT ?`,
    );
    const priceStmt = db.prepare(
      `SELECT date, close FROM prices WHERE ticker = ?
       ORDER BY date DESC LIMIT ?`,
    );
    // Only the most recent geo snapshot: it refreshes weekly, and the panel shows a
    // current picture rather than a history.
    const geoStmt = db.prepare(
      `SELECT country, interest FROM theme_geo
       WHERE theme_id = ? AND date = (SELECT MAX(date) FROM theme_geo WHERE theme_id = ?)
       ORDER BY interest DESC`,
    );

    const out: ThemeData[] = themes.map((t) => {
      const history = (
        historyStmt.all(t.id, HISTORY_DAYS) as HistoryPoint[]
      ).reverse();
      const latest = history.length ? history[history.length - 1] : null;

      const etf = t.basket.etf;
      const etfPrices = etf
        ? ((priceStmt.all(etf, HISTORY_DAYS) as PricePoint[]).reverse())
        : [];

      const tickers = [...t.basket.stocks, ...(etf ? [etf] : [])];
      const quotes: BasketQuote[] = tickers.map((ticker) => {
        const series = (
          priceStmt.all(ticker, HISTORY_DAYS) as PricePoint[]
        ).reverse();
        return {
          ticker,
          latest: series.length ? series[series.length - 1].close : null,
          change7d: pct7d(series),
        };
      });

      return {
        id: t.id,
        name: t.name,
        category: t.category,
        basket: t.basket,
        date_added: t.date_added,
        geo: t.geo ?? { footprint: [], listings: {} },
        geoInterest: geoStmt.all(t.id, t.id) as GeoInterest[],
        latest,
        history,
        etfPrices,
        quotes,
      };
    });

    const concentration = (
      db
        .prepare(
          `SELECT date, hhi, top5_share,
                  breadth_early, breadth_crowded, breadth_froth, breadth_dormant
           FROM market_concentration ORDER BY date DESC LIMIT ?`,
        )
        .all(HISTORY_DAYS) as ConcentrationPoint[]
    ).reverse();

    return { asOf, themes: out, concentration, institutions: getInstitutions(db, themes) };
  } finally {
    db.close();
  }
}

/** Manager style lookup mirrors collector/sources/managers.py. */
const MANAGER_STYLES: Record<string, string> = {
  blackrock: "passive", vanguard: "passive", "state-street": "passive", geode: "passive",
  jpmorgan: "bank", goldman: "bank", "morgan-stanley": "bank", ubs: "bank",
};

function getInstitutions(db: Database.Database, themes: RawTheme[]): Institutions {
  const quarters = (
    db.prepare("SELECT DISTINCT quarter FROM institutional_holdings ORDER BY quarter DESC LIMIT 2")
      .all() as { quarter: string }[]
  ).map((r) => r.quarter);
  const quarter = quarters[0] ?? null;
  const prevQuarter = quarters[1] ?? null;

  // ticker -> themes (a ticker can belong to several, e.g. DLR in AI infra and REITs)
  const themesByTicker = new Map<string, string[]>();
  for (const t of themes) {
    const tickers = [...t.basket.stocks, ...(t.basket.etf ? [t.basket.etf] : [])];
    for (const tk of tickers) {
      themesByTicker.set(tk, [...(themesByTicker.get(tk) ?? []), t.id]);
    }
  }

  // theme -> style -> {value, prev}
  const agg = new Map<string, Map<string, { value: number; prev: number }>>();
  if (quarter) {
    const rows = db
      .prepare(
        `SELECT quarter, manager, ticker, value_usd FROM institutional_holdings
         WHERE quarter = ? OR quarter = ?`,
      )
      .all(quarter, prevQuarter ?? quarter) as {
      quarter: string; manager: string; ticker: string; value_usd: number;
    }[];
    for (const r of rows) {
      const style = MANAGER_STYLES[r.manager] ?? "active";
      for (const themeId of themesByTicker.get(r.ticker) ?? []) {
        const byStyle = agg.get(themeId) ?? new Map();
        const cur = byStyle.get(style) ?? { value: 0, prev: 0 };
        if (r.quarter === quarter) cur.value += r.value_usd ?? 0;
        else cur.prev += r.value_usd ?? 0;
        byStyle.set(style, cur);
        agg.set(themeId, byStyle);
      }
    }
  }

  const instThemes: InstitutionalTheme[] = [...agg.entries()].map(([theme_id, byStyle]) => {
    const styles: StyleHolding[] = [...byStyle.entries()].map(([style, v]) => ({
      style, value: v.value, prev: v.prev, delta: v.value - v.prev,
    }));
    const total = styles.reduce((s, x) => s + x.value, 0);
    const prev_total = styles.reduce((s, x) => s + x.prev, 0);
    return {
      theme_id, quarter: quarter ?? "", prev_quarter: prevQuarter,
      total, prev_total, delta: total - prev_total,
      byStyle: styles.sort((a, b) => b.value - a.value),
    };
  });

  // ---- analyst actions, rolled up per theme
  const actionStmt = db.prepare(
    `SELECT date, ticker, firm, action, from_grade, to_grade FROM analyst_actions
     WHERE ticker IN (SELECT value FROM json_each(?)) ORDER BY date DESC`,
  );
  const analystThemes: AnalystTheme[] = [];
  for (const t of themes) {
    const tickers = [...t.basket.stocks, ...(t.basket.etf ? [t.basket.etf] : [])];
    let actions: AnalystAction[] = [];
    try {
      actions = actionStmt.all(JSON.stringify(tickers)) as AnalystAction[];
    } catch {
      actions = [];
    }
    if (!actions.length) continue;
    const upgrades = actions.filter((a) => a.action === "up").length;
    const downgrades = actions.filter((a) => a.action === "down").length;
    analystThemes.push({
      theme_id: t.id,
      upgrades,
      downgrades,
      net: upgrades - downgrades,
      recent: actions.slice(0, 6),
    });
  }

  return { quarter, prevQuarter, themes: instThemes, analysts: analystThemes };
}
