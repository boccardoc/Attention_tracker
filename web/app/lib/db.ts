import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import type {
  Basket,
  BasketQuote,
  ConcentrationPoint,
  HistoryPoint,
  PricePoint,
  ScoresResponse,
  ThemeData,
} from "./types";

const HISTORY_DAYS = 180;

interface RawTheme {
  id: string;
  name: string;
  category: string;
  basket: Basket;
  date_added: string;
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

    return { asOf, themes: out, concentration };
  } finally {
    db.close();
  }
}
