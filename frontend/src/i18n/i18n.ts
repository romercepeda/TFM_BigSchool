// i18n — Spec D10 §9 + Spec D08 §5.
// t(key, params) → translated string with {placeholder} interpolation.
//
// Locales are statically imported so Vite tracks them for HMR and tree-shaking.

import { currentLanguage } from '../state/language-state.js';
import esBundle from './locales/es.json';
import enBundle from './locales/en.json';

type Bundle = Record<string, string>;

const BUNDLES: Record<string, Bundle> = {
  es: esBundle as Bundle,
  en: enBundle as Bundle,
};

let _activeBundle: Bundle = BUNDLES['es'] ?? {};
let _fallbackBundle: Bundle = BUNDLES['es'] ?? {};

export async function loadLocale(lang: string, fallback = 'es'): Promise<void> {
  _activeBundle   = BUNDLES[lang]     ?? BUNDLES[fallback] ?? {};
  _fallbackBundle = BUNDLES[fallback] ?? {};
  currentLanguage.value = lang;
}

export function t(key: string, params?: Record<string, string | number>): string {
  let text = _activeBundle[key] ?? _fallbackBundle[key] ?? key;
  if (params) {
    text = text.replace(/\{(\w+)\}/g, (_m, k: string) => String(params[k] ?? `{${k}}`));
  }
  return text;
}
