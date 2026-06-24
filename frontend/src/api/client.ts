// Thin fetch wrapper — Spec D10 §7.1.
// Centralizes: base URL, credentials, Accept-Language, CSRF header,
// error normalization, and 401 → /login redirect.

import { ApiError } from './types.js';
import { currentLanguage } from '../state/language-state.js';
import { navigate } from '../router/router.js';
import { clearAuthState } from '../state/auth-state.js';

const BASE_URL: string = import.meta.env.VITE_BACKEND_BASE_URL ?? 'http://localhost:8000';

function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)pi_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const safeMethods = new Set(['GET', 'HEAD', 'OPTIONS']);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept-Language': currentLanguage.value,
  };

  if (!safeMethods.has(method.toUpperCase())) {
    const csrf = getCsrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    clearAuthState();
    navigate('/login');
    throw new ApiError(401, 'unauthorized', 'Session expired. Please log in again.');
  }

  if (!res.ok) {
    let detail = 'Request failed.';
    let code = `http_${res.status}`;
    let details: { field?: string; message: string }[] = [];
    try {
      const json = await res.json() as { detail?: unknown };
      if (typeof json.detail === 'string') {
        detail = json.detail;
      } else if (Array.isArray(json.detail)) {
        details = (json.detail as { loc?: string[]; msg: string }[]).map((e) => ({
          field: e.loc?.slice(1).join('.'),
          message: e.msg,
        }));
        detail = details[0]?.message ?? detail;
      }
    } catch {
      // non-JSON error body — keep defaults
    }
    throw new ApiError(res.status, code, detail, details);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const get  = <T>(path: string)                  => request<T>('GET',    path);
export const post = <T>(path: string, body?: unknown)  => request<T>('POST',   path, body);
export const patch = <T>(path: string, body?: unknown) => request<T>('PATCH',  path, body);
export const put  = <T>(path: string, body?: unknown)  => request<T>('PUT',    path, body);
export const del  = <T>(path: string)                  => request<T>('DELETE', path);
