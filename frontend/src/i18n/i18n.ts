// i18n — Spec D10 §9 + Spec D08 §5.
// t(key, params) → translated string with {placeholder} interpolation.

import { currentLanguage } from '../state/language-state.js';

type Bundle = Record<string, string>;

const _cache = new Map<string, Bundle>();

async function _loadBundle(lang: string): Promise<Bundle> {
  const cached = _cache.get(lang);
  if (cached) return cached;
  try {
    const mod = await import(`./locales/${lang}.json`, { assert: { type: 'json' } }) as { default: Bundle };
    _cache.set(lang, mod.default);
    return mod.default;
  } catch {
    return {};
  }
}

let _activeBundle: Bundle = {};
let _fallbackBundle: Bundle = {};

export async function loadLocale(lang: string, fallback = 'es'): Promise<void> {
  [_activeBundle, _fallbackBundle] = await Promise.all([
    _loadBundle(lang),
    _loadBundle(fallback),
  ]);
  currentLanguage.value = lang;
}

export function t(key: string, params?: Record<string, string | number>): string {
  let text = _activeBundle[key] ?? _fallbackBundle[key] ?? key;
  if (params) {
    text = text.replace(/\{(\w+)\}/g, (_m, k: string) => String(params[k] ?? `{${k}}`));
  }
  return text;
}
