import { signal } from '@preact/signals-core';
import type { Theme } from '../config/app-config.js';

const STORAGE_KEY = 'pi_theme';
const DEFAULT_THEME: Theme = 'pastel';

function readStoredTheme(): Theme {
  try {
    return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export const currentTheme = signal<Theme>(readStoredTheme());

export function applyTheme(theme: Theme): void {
  if (theme === 'default') {
    delete document.documentElement.dataset['theme'];
  } else {
    document.documentElement.dataset['theme'] = theme;
  }
}

export function setTheme(theme: Theme): void {
  currentTheme.value = theme;
  applyTheme(theme);
  try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* storage not available */ }
}
