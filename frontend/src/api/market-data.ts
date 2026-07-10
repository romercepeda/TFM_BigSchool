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

export const getAssetPrice  = (ticker: string, exchange?: string | null) => {
  const qs = exchange ? `?exchange=${encodeURIComponent(exchange)}` : '';
  return get<PricePoint>(`/market-data/assets/${encodeURIComponent(ticker)}/price${qs}`);
};

export const runDailyUpdate = () =>
  post<DailyUpdateResult>('/market-data/daily-update');
