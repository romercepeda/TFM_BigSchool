import { get, post, patch, del } from './client.js';
import type { DateAlert } from './types.js';

export interface DateAlertInput {
  alert_date: string;
  description: string;
}

export interface UpdateDateAlertBody {
  alert_date?: string;
  description?: string;
}

const basePath = (portfolioId: string, holdingId: string): string =>
  `/portfolios/${portfolioId}/holdings/${holdingId}/date-alerts`;

export const listDateAlerts = (portfolioId: string, holdingId: string) =>
  get<DateAlert[]>(basePath(portfolioId, holdingId));

export const createDateAlert = (portfolioId: string, holdingId: string, body: DateAlertInput) =>
  post<DateAlert>(basePath(portfolioId, holdingId), body);

export const updateDateAlert = (portfolioId: string, holdingId: string, alertId: string, body: UpdateDateAlertBody) =>
  patch<DateAlert>(`${basePath(portfolioId, holdingId)}/${alertId}`, body);

export const deleteDateAlert = (portfolioId: string, holdingId: string, alertId: string) =>
  del<void>(`${basePath(portfolioId, holdingId)}/${alertId}`);

export const markDateAlertSeen = (portfolioId: string, holdingId: string, alertId: string) =>
  post<DateAlert>(`${basePath(portfolioId, holdingId)}/${alertId}/mark-read`);
