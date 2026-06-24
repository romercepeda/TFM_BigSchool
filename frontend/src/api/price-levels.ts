import { get, post, patch, del } from './client.js';
import type { PriceLevel } from './types.js';

export interface CreateLevelBody {
  price: number;
  direction: 'above' | 'below';
  label?: string;
  per?: number[];
}

export const listPriceLevels  = (holdingId: string)                          => get<PriceLevel[]>(`/holdings/${holdingId}/price-levels`);
export const createPriceLevel = (holdingId: string, body: CreateLevelBody)   => post<PriceLevel>(`/holdings/${holdingId}/price-levels`, body);
export const updatePriceLevel = (holdingId: string, levelId: string, body: Partial<CreateLevelBody>) =>
  patch<PriceLevel>(`/holdings/${holdingId}/price-levels/${levelId}`, body);
export const deletePriceLevel = (holdingId: string, levelId: string)         => del<void>(`/holdings/${holdingId}/price-levels/${levelId}`);
export const dismissAlert     = (holdingId: string, levelId: string)         =>
  post<PriceLevel>(`/holdings/${holdingId}/price-levels/${levelId}/dismiss`);
