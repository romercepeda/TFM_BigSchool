import { get, put } from './client.js';
import type { IndicatorSnapshot, Indicator, IndicatorSnapshotHistory } from './types.js';

export const listIndicators     = ()                  => get<Indicator[]>('/indicators');
export const getAssetIndicators = (assetId: string)   => get<IndicatorSnapshotHistory[]>(`/assets/${assetId}/indicators`);
export const getSnapshotHistory = (assetId: string, code: string, limit = 30) =>
  get<IndicatorSnapshotHistory>(`/assets/${assetId}/indicators/${code}/history?limit=${limit}`);

// Admin-only (permission indicator.manual_override) — post-v1 user request.
export interface ManualIndicatorValueIn {
  as_of_date: string;
  value_numeric?: number;
  value_text?: string;
}

export const setIndicatorManualValue = (
  assetId: string, indicatorId: string, body: ManualIndicatorValueIn,
) =>
  put<IndicatorSnapshot>(`/assets/${assetId}/indicators/${indicatorId}/manual-value`, body);
