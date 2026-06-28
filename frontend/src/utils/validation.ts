// Client-side form validation helpers — Spec D10 §11.
// All functions return an i18n error key on failure, or null on success.

export function required(value: string): string | null {
  return value.trim() ? null : 'validation.required';
}

export function email(value: string): string | null {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? null : 'validation.email';
}

export function minLength(value: string, min: number): string | null {
  return value.length >= min ? null : 'validation.min_length';
}

export function maxLength(value: string, max: number): string | null {
  return value.length <= max ? null : 'validation.max_length';
}

export function positiveNumber(value: string): string | null {
  const n = Number(value);
  return !isNaN(n) && n > 0 ? null : 'validation.number.positive';
}

export function nonNegativeNumber(value: string): string | null {
  const n = Number(value);
  return !isNaN(n) && n >= 0 ? null : 'validation.non_negative_number';
}

export function first(...validators: Array<() => string | null>): string | null {
  for (const v of validators) {
    const err = v();
    if (err) return err;
  }
  return null;
}
