import { get } from './client.js';
import type { Indicator, IndicatorSnapshotHistory } from './types.js';

export const listIndicators     = ()                  => get<Indicator[]>('/indicators');
export const getAssetIndicators = (assetId: string)   => get<IndicatorSnapshotHistory[]>(`/assets/${assetId}/indicators`);
export const getSnapshotHistory = (assetId: string, code: string, limit = 30) =>
  get<IndicatorSnapshotHistory>(`/assets/${assetId}/indicators/${code}/history?limit=${limit}`);
