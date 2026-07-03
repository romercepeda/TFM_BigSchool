import { get, put, post } from './client.js';
import type { DataProvidersResponse } from './types.js';

export const getDataProviders = () => get<DataProvidersResponse>('/settings/data-providers');

export const updateDataProviders = (marketDataProviders: string[], fxDataProviders: string[]) =>
  put<DataProvidersResponse>('/settings/data-providers', {
    market_data_providers: marketDataProviders,
    fx_data_providers: fxDataProviders,
  });

export const resetDataProviders = () =>
  post<DataProvidersResponse>('/settings/data-providers/reset');
