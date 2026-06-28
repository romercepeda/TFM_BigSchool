import { get, post, patch, del } from './client.js';
import type { Portfolio, PortfolioKpis } from './types.js';

export interface CreatePortfolioBody { name: string; base_currency: string; }
export interface UpdatePortfolioBody { name?: string; }

export const listPortfolios   = (include_archived = false)   =>
  get<Portfolio[]>(`/portfolios${include_archived ? '?include_archived=true' : ''}`);
export const getPortfolio     = (id: string)                 => get<Portfolio>(`/portfolios/${id}`);
export const createPortfolio  = (body: CreatePortfolioBody)  => post<Portfolio>('/portfolios', body);
export const updatePortfolio  = (id: string, body: UpdatePortfolioBody) =>
  patch<Portfolio>(`/portfolios/${id}`, body);
export const archivePortfolio = (id: string)                 => post<Portfolio>(`/portfolios/${id}/archive`);
export const restorePortfolio = (id: string)                 => post<Portfolio>(`/portfolios/${id}/restore`);
export const deletePortfolio  = (id: string)                 => del<void>(`/portfolios/${id}`);
export const getPortfolioKpis = (id: string)                 => get<PortfolioKpis>(`/portfolios/${id}/kpis`);
