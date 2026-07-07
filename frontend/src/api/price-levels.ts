import { get, post, patch, del } from './client.js';
import type { PriceLevel, PriceLevelDirection } from './types.js';

export interface PriceLevelInput {
  direction: PriceLevelDirection;
  target_price: number;
  note?: string;
}

export interface CreatePriceLevelsBody {
  levels: PriceLevelInput[];
  asset_price_at_event?: number;
}

export interface UpdatePriceLevelBody {
  direction?: PriceLevelDirection;
  target_price?: number;
  note?: string;
  asset_price_at_event?: number;
}

const basePath = (portfolioId: string, holdingId: string): string =>
  `/portfolios/${portfolioId}/holdings/${holdingId}/price-levels`;

export const listPriceLevels = (portfolioId: string, holdingId: string) =>
  get<PriceLevel[]>(basePath(portfolioId, holdingId));

export const createPriceLevels = (portfolioId: string, holdingId: string, body: CreatePriceLevelsBody) =>
  post<PriceLevel[]>(basePath(portfolioId, holdingId), body);

export const updatePriceLevel = (portfolioId: string, holdingId: string, levelId: string, body: UpdatePriceLevelBody) =>
  patch<PriceLevel>(`${basePath(portfolioId, holdingId)}/${levelId}`, body);

export const deletePriceLevel = (portfolioId: string, holdingId: string, levelId: string, assetPriceAtEvent?: number) =>
  del<void>(
    `${basePath(portfolioId, holdingId)}/${levelId}`,
    assetPriceAtEvent !== undefined ? { asset_price_at_event: assetPriceAtEvent } : undefined,
  );
