export interface Basket {
  etf: string | null;
  stocks: string[];
}

export interface HistoryPoint {
  date: string;
  research_z: number | null;
  speculative_z: number | null;
  research_velocity_7d: number | null;
  speculative_velocity_7d: number | null;
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
  latest: HistoryPoint | null;
  history: HistoryPoint[];
  etfPrices: PricePoint[]; // basket ETF series for the detail overlay
  quotes: BasketQuote[]; // latest + 7d change for every basket ticker (etf + stocks)
}

export interface ScoresResponse {
  asOf: string | null;
  themes: ThemeData[];
}
