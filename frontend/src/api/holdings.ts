import { get, post, patch, del } from './client.js';
import type { Holding, HoldingAsset, Lot, Sale } from './types.js';

export interface AssetPatchBody { ticker?: string; name?: string; market?: string; }

export const updateAsset = (assetId: string, body: AssetPatchBody) =>
  patch<HoldingAsset>(`/assets/${assetId}`, body);

export interface AssetIn {
  ticker: string;
  name: string;
  asset_type: string;
  quote_currency: string;
  market: string | null;
}

export interface LotIn {
  purchase_date: string;
  quantity: number;
  unit_price: number;
  fx_rate_origin?: string;
  notes?: string;
}

export interface AddAssetBody { asset: AssetIn; lot: LotIn; }
export interface AddLotBody   { purchase_date: string; quantity: number; unit_price: number; notes?: string; fx_rate_origin?: string; }

export const listHoldings  = (portfolioId: string)               => get<Holding[]>(`/portfolios/${portfolioId}/holdings`);
export const getHolding    = (portfolioId: string, id: string)   => get<Holding>(`/portfolios/${portfolioId}/holdings/${id}`);
export const addAsset      = (portfolioId: string, body: AddAssetBody) =>
  post<Holding>(`/portfolios/${portfolioId}/holdings`, body);
export const deleteHolding = (portfolioId: string, id: string)   => del<void>(`/portfolios/${portfolioId}/holdings/${id}`);

export const listLots  = (portfolioId: string, holdingId: string) =>
  get<Lot[]>(`/portfolios/${portfolioId}/holdings/${holdingId}/lots`);
export const addLot    = (portfolioId: string, holdingId: string, body: AddLotBody) =>
  post<Lot>(`/portfolios/${portfolioId}/holdings/${holdingId}/lots`, body);
export const updateLot = (portfolioId: string, holdingId: string, lotId: string, body: Partial<AddLotBody>) =>
  patch<Lot>(`/portfolios/${portfolioId}/holdings/${holdingId}/lots/${lotId}`, body);
export const deleteLot = (portfolioId: string, holdingId: string, lotId: string) =>
  del<void>(`/portfolios/${portfolioId}/holdings/${holdingId}/lots/${lotId}`);

// create/update/delete a Sale live in api/sales.ts (Spec D13 §7) — FIFO lot
// selection happens server-side, unlike the lot_id-based shape this file
// used to declare (never wired to any screen; removed rather than kept
// wrong-but-unused).
export const listSales = (portfolioId: string, holdingId: string) =>
  get<Sale[]>(`/portfolios/${portfolioId}/holdings/${holdingId}/sales`);
