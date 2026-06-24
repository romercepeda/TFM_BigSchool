// Intl wrappers — Spec D08 §7, Spec D10 §9.
// All formatters read currentLanguage.value so they respond to language changes.

import { currentLanguage } from '../state/language-state.js';

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(currentLanguage.value, options).format(value);
}

export function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat(currentLanguage.value, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number, decimals = 2): string {
  return new Intl.NumberFormat(currentLanguage.value, {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value / 100);
}

export function formatDate(value: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  return new Intl.DateTimeFormat(currentLanguage.value, options ?? { dateStyle: 'medium' }).format(date);
}

export function formatDateTime(value: string | Date): string {
  return formatDate(value, { dateStyle: 'medium', timeStyle: 'short' });
}
