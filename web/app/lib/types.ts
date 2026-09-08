export interface Basket {
  etf: string | null;
  stocks: string[];
}

/** Curated: where the industry physically operates. Ordered most-significant-first. */
export interface ThemeGeo {
  footprint: string[];                    // ISO-3166 alpha-2
  listings: Record<string, string>;       // ticker -> ISO2
}

/** Live: which countries search for this theme (Google Trends, 0-100 within theme). */
export interface GeoInterest {
  country: string;                        // ISO-3166 alpha-2
  interest: number;
}

export interface HistoryPoint {
  date: string;
  research_z: number | null;
  speculative_z: number | null;
  sentiment_z: number | null;
  research_velocity_7d: number | null;
  speculative_velocity_7d: number | null;
  sentiment_velocity_7d: number | null;
  /** Share of ALL themes' attention that day (0-1). Sums to 1 across themes. */
  share_pct: number | null;
}

/** One day of market-wide concentration — how narrow is attention overall. */
export interface ConcentrationPoint {
  date: string;
  hhi: number | null;
  top5_share: number | null;
  breadth_early: number | null;
  breadth_crowded: number | null;
  breadth_froth: number | null;
  breadth_dormant: number | null;
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface BasketQuote {
  ticker: string;
  latest: number | null;
  change7d: number | null; // fractional, e.g. 0.034 = +3.4%
}

export interface ThemeData {
  id: string;
  name: string;
  category: string;
  basket: Basket;
  date_added: string;
  geo: ThemeGeo;
  /** Empty until the weekly Trends geo refresh has run at least once. */
  geoInterest: GeoInterest[];
  latest: HistoryPoint | null;
  history: HistoryPoint[];
  etfPrices: PricePoint[]; // basket ETF series for the detail overlay
  quotes: BasketQuote[]; // latest + 7d change for every basket ticker (etf + stocks)
}

export interface ScoresResponse {
  asOf: string | null;
  themes: ThemeData[];
  /** 180-day market-wide concentration series, oldest first. */
  concentration: ConcentrationPoint[];
}
