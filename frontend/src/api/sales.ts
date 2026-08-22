// Sale API client — Spec D13 §7. FIFO lot selection happens server-side
// (no lot_id in the request body — see Changeset C20 §2).
// listSales lives in api/holdings.ts (already used by history-screen.ts) —
// not duplicated here.
import { post, patch, del } from './client.js';
import type { Sale, SalePreview } from './types.js';

export interface SaleIn {
  sale_date: string;
  quantity: number;
  unit_price: number;
  fx_rate_at_sale?: number;
  fx_rate_origin?: string;
  notes?: string;
}

export const previewSale = (portfolioId: string, holdingId: string, body: SaleIn) =>
  post<SalePreview>(`/portfolios/${portfolioId}/holdings/${holdingId}/sales/preview`, body);

export const createSale = (portfolioId: string, holdingId: string, body: SaleIn) =>
  post<Sale>(`/portfolios/${portfolioId}/holdings/${holdingId}/sales`, body);

export const updateSaleReason = (portfolioId: string, holdingId: string, saleId: string, notes: string) =>
  patch<Sale>(`/portfolios/${portfolioId}/holdings/${holdingId}/sales/${saleId}`, { notes });

export const deleteSale = (portfolioId: string, holdingId: string, saleId: string) =>
  del<void>(`/portfolios/${portfolioId}/holdings/${holdingId}/sales/${saleId}`);
