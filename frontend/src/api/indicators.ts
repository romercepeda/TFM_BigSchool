import { get } from './client.js';
import type { Indicator, IndicatorSnapshot } from './types.js';

export const listIndicators       = ()                           => get<Indicator[]>('/indicators');
export const getHoldingSnapshots  = (holdingId: string)         => get<IndicatorSnapshot[]>(`/holdings/${holdingId}/indicators`);
export const getSnapshotHistory   = (holdingId: string, code: string, limit = 30) =>
  get<IndicatorSnapshot[]>(`/holdings/${holdingId}/indicators/${code}/history?limit=${limit}`);
