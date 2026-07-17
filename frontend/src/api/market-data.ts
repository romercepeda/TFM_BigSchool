import { get, post } from './client.js';
import type { AssetSearchResult } from './types.js';

export interface DailyUpdateResult {
  assets_processed: number;
  assets_failed: number;
  alerts_triggered: number;
  indicator_snapshots: number;
  ran_at: string;
}

export interface PricePoint {
  ticker: string;
  as_of_date: string;
  price: number;
  fetched_at: string;
}

export const searchAssets   = (q: string) =>
  get<AssetSearchResult[]>(`/market-data/assets/search?q=${encodeURIComponent(q)}`);

// Cache-only — reads the last known price (daily job or a prior manual
// refresh). Does not call the live provider (Changeset C19).
export const getAssetPrice  = (ticker: string, exchange?: string | null) => {
  const qs = exchange ? `?exchange=${encodeURIComponent(exchange)}` : '';
  return get<PricePoint>(`/market-data/assets/${encodeURIComponent(ticker)}/price${qs}`);
};

// Live re-fetch, on demand — the refresh icon on the asset detail screen's
// "Current Price" card (Changeset C19). Persisted server-side as today's
// AssetPriceHistory row, so it survives leaving and re-entering the screen.
export const refreshAssetPrice = (ticker: string, exchange?: string | null) => {
  const qs = exchange ? `?exchange=${encodeURIComponent(exchange)}` : '';
  return post<PricePoint>(`/market-data/assets/${encodeURIComponent(ticker)}/price/refresh${qs}`);
};

export const runDailyUpdate = () =>
  post<DailyUpdateResult>('/market-data/daily-update');
