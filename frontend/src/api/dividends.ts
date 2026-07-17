// Dividend Tracking API client — Spec D15. Two scopes, mirroring the backend:
//   - schedule: asset-scoped (/assets/{id}/dividend-schedule)
//   - payments: holding-scoped (/portfolios/{id}/holdings/{id}/dividend-payments)
import { get, post, patch, put, del } from './client.js';
import type { DividendFrequency, DividendPayment, DividendSchedule } from './types.js';

export interface DividendScheduleIn {
  frequency: DividendFrequency;
  amount_per_payment: number;
  next_payment_date?: string | null;
  notes?: string | null;
}

export const getDividendSchedule = (assetId: string) =>
  get<DividendSchedule>(`/assets/${assetId}/dividend-schedule`);

export const upsertDividendSchedule = (assetId: string, body: DividendScheduleIn) =>
  put<DividendSchedule>(`/assets/${assetId}/dividend-schedule`, body);

export const deleteDividendSchedule = (assetId: string) =>
  del<void>(`/assets/${assetId}/dividend-schedule`);

export interface DividendPaymentIn {
  payment_date: string;
  gross_amount_quote: number;
  fx_rate_origin?: string;
  notes?: string | null;
}

export const listDividendPayments = (portfolioId: string, holdingId: string) =>
  get<DividendPayment[]>(`/portfolios/${portfolioId}/holdings/${holdingId}/dividend-payments`);

export const createDividendPayment = (portfolioId: string, holdingId: string, body: DividendPaymentIn) =>
  post<DividendPayment>(`/portfolios/${portfolioId}/holdings/${holdingId}/dividend-payments`, body);

export const updateDividendPaymentNotes = (
  portfolioId: string, holdingId: string, paymentId: string, notes: string,
) =>
  patch<DividendPayment>(
    `/portfolios/${portfolioId}/holdings/${holdingId}/dividend-payments/${paymentId}`, { notes },
  );

export const deleteDividendPayment = (portfolioId: string, holdingId: string, paymentId: string) =>
  del<void>(`/portfolios/${portfolioId}/holdings/${holdingId}/dividend-payments/${paymentId}`);
