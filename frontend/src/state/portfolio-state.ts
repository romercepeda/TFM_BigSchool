import { signal } from '@preact/signals-core';
import type { Portfolio } from '../api/types.js';

export const activePortfolio = signal<Portfolio | null>(null);
