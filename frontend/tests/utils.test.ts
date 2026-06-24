// Unit tests for pure utility functions — Spec D10 §12 + Spec 00c §2.

import { describe, it, expect, beforeEach } from 'vitest';
import { required, email, minLength, positiveNumber, first } from '../src/utils/validation.js';

describe('validation', () => {
  describe('required', () => {
    it('returns null for non-empty string', () => {
      expect(required('hello')).toBeNull();
    });
    it('returns error key for empty string', () => {
      expect(required('')).toBe('validation.required');
    });
    it('returns error key for whitespace-only string', () => {
      expect(required('   ')).toBe('validation.required');
    });
  });

  describe('email', () => {
    it('accepts valid email', () => {
      expect(email('user@example.com')).toBeNull();
    });
    it('rejects missing @', () => {
      expect(email('notanemail')).toBe('validation.email');
    });
    it('rejects missing domain', () => {
      expect(email('user@')).toBe('validation.email');
    });
  });

  describe('minLength', () => {
    it('accepts string at minimum', () => {
      expect(minLength('12345678', 8)).toBeNull();
    });
    it('rejects string below minimum', () => {
      expect(minLength('short', 8)).toBe('validation.min_length');
    });
  });

  describe('positiveNumber', () => {
    it('accepts positive number string', () => {
      expect(positiveNumber('42')).toBeNull();
      expect(positiveNumber('0.01')).toBeNull();
    });
    it('rejects zero', () => {
      expect(positiveNumber('0')).toBe('validation.positive_number');
    });
    it('rejects negative', () => {
      expect(positiveNumber('-5')).toBe('validation.positive_number');
    });
    it('rejects non-numeric', () => {
      expect(positiveNumber('abc')).toBe('validation.positive_number');
    });
  });

  describe('first', () => {
    it('returns null when all pass', () => {
      expect(first(() => null, () => null)).toBeNull();
    });
    it('returns first error', () => {
      expect(first(() => 'error.a', () => 'error.b')).toBe('error.a');
    });
    it('skips passing validators', () => {
      expect(first(() => null, () => 'error.b')).toBe('error.b');
    });
  });
});

describe('router', () => {
  // Import route matching separately to avoid DOM/window side effects.
  const { matchRoute } = await import('../src/router/routes.js');

  it('matches /login as login screen (no auth)', () => {
    const m = matchRoute('/login');
    expect(m?.screen).toBe('pi-login-screen');
    expect(m?.authRequired).toBe(false);
  });

  it('matches /portfolios', () => {
    expect(matchRoute('/portfolios')?.screen).toBe('pi-portfolios-screen');
  });

  it('extracts portfolioId param', () => {
    const m = matchRoute('/portfolios/abc-123');
    expect(m?.screen).toBe('pi-dashboard-screen');
    expect(m?.params['portfolioId']).toBe('abc-123');
  });

  it('extracts both params on deep route', () => {
    const m = matchRoute('/portfolios/p1/assets/h2/levels');
    expect(m?.screen).toBe('pi-set-levels-screen');
    expect(m?.params['portfolioId']).toBe('p1');
    expect(m?.params['holdingId']).toBe('h2');
  });

  it('returns null for unknown path', () => {
    expect(matchRoute('/does-not-exist')).toBeNull();
  });
});
