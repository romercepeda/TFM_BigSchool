// Central app configuration.
// To add a new theme:
//   1. Create src/styles/themes/<name>.css with [data-theme="<name>"] { --color-*: ...; }
//   2. Import it in main.ts
//   3. Add the name to the Theme union and an entry to THEMES below.

export type Theme = 'default' | 'pastel' | 'dark' | 'ocean' | 'forest';

export interface ThemeInfo {
  readonly id: Theme;
  readonly labelKey: string;
  // Preview swatch colors (hardcoded — don't use CSS vars here, these render in HTML attributes)
  readonly swatchBg: string;
  readonly swatchAccent: string;
  readonly swatchBorder: string;
}

export const THEMES: readonly ThemeInfo[] = [
  {
    id: 'default',
    labelKey: 'settings.theme.default',
    swatchBg: '#f8fafc', swatchAccent: '#2563eb', swatchBorder: '#e2e8f0',
  },
  {
    id: 'pastel',
    labelKey: 'settings.theme.pastel',
    swatchBg: '#f0ebff', swatchAccent: '#8677f0', swatchBorder: '#ddd6ff',
  },
  {
    id: 'dark',
    labelKey: 'settings.theme.dark',
    swatchBg: '#1e1e2e', swatchAccent: '#89b4fa', swatchBorder: '#45475a',
  },
  {
    id: 'ocean',
    labelKey: 'settings.theme.ocean',
    swatchBg: '#e0f2fe', swatchAccent: '#0284c7', swatchBorder: '#7dd3fc',
  },
  {
    id: 'forest',
    labelKey: 'settings.theme.forest',
    swatchBg: '#f0f4e8', swatchAccent: '#2d7a22', swatchBorder: '#c5d9b0',
  },
];
