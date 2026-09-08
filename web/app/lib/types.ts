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

/** 13F: what a manager style held in a theme's basket, and the quarter-over-quarter move. */
export interface StyleHolding {
  style: string;          // 'passive' | 'active' | 'bank'
  value: number;
  prev: number;
  delta: number;
}

export interface InstitutionalTheme {
  theme_id: string;
  quarter: string;
  prev_quarter: string | null;
  total: number;
  prev_total: number;
  delta: number;
  byStyle: StyleHolding[];
}

/** Sell-side rating action, with the firm named. */
export interface AnalystAction {
  date: string;
  ticker: string;
  firm: string;
  action: string;
  from_grade: string;
  to_grade: string;
}

export interface AnalystTheme {
  theme_id: string;
  upgrades: number;
  downgrades: number;
  net: number;
  recent: AnalystAction[];
}

export interface Institutions {
  /** 13F period the holdings describe. Filed up to 45 days after this date. */
  quarter: string | null;
  prevQuarter: string | null;
  themes: InstitutionalTheme[];
  analysts: AnalystTheme[];
}

export interface ScoresResponse {
  asOf: string | null;
  themes: ThemeData[];
  /** 180-day market-wide concentration series, oldest first. */
  concentration: ConcentrationPoint[];
  /** 13F positioning + sell-side actions. Separate from the daily attention channels. */
  institutions: Institutions;
}
