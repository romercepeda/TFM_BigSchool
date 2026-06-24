import { get, post, patch, del } from './client.js';
import type { Holding, Lot, Sale } from './types.js';

export interface AddAssetBody { ticker: string; quantity: number; cost_per_unit: number; acquired_at: string; notes?: string; }
export interface AddLotBody   { quantity: number; cost_per_unit: number; acquired_at: string; notes?: string; }
export interface AddSaleBody  { lot_id: string; quantity: number; price_per_unit: number; sold_at: string; }

export const listHoldings  = (portfolioId: string)               => get<Holding[]>(`/portfolios/${portfolioId}/holdings`);
export const getHolding    = (portfolioId: string, id: string)   => get<Holding>(`/portfolios/${portfolioId}/holdings/${id}`);
export const addAsset      = (portfolioId: string, body: AddAssetBody) =>
  post<Holding>(`/portfolios/${portfolioId}/holdings`, body);
export const deleteHolding = (portfolioId: string, id: string)   => del<void>(`/portfolios/${portfolioId}/holdings/${id}`);

export const listLots  = (holdingId: string)             => get<Lot[]>(`/holdings/${holdingId}/lots`);
export const addLot    = (holdingId: string, body: AddLotBody) => post<Lot>(`/holdings/${holdingId}/lots`, body);
export const updateLot = (holdingId: string, lotId: string, body: Partial<AddLotBody>) =>
  patch<Lot>(`/holdings/${holdingId}/lots/${lotId}`, body);
export const deleteLot = (holdingId: string, lotId: string)  => del<void>(`/holdings/${holdingId}/lots/${lotId}`);

export const listSales = (holdingId: string)              => get<Sale[]>(`/holdings/${holdingId}/sales`);
export const addSale   = (holdingId: string, body: AddSaleBody) => post<Sale>(`/holdings/${holdingId}/sales`, body);
export const deleteSale = (holdingId: string, saleId: string) => del<void>(`/holdings/${holdingId}/sales/${saleId}`);
