import { signal } from '@preact/signals-core';
import type { LoginUserOut } from '../api/types.js';

export const currentUser = signal<LoginUserOut | null>(null);
export const pollIntervalSeconds = signal<number>(30);

export function setAuthState(user: LoginUserOut, pollInterval: number): void {
  currentUser.value = user;
  pollIntervalSeconds.value = pollInterval;
}

export function clearAuthState(): void {
  currentUser.value = null;
}

// Updates the user portion only — e.g. after /auth/change-password or
// /me/refresh-permissions, where the session (poll interval) is unchanged.
export function updateCurrentUser(user: LoginUserOut): void {
  currentUser.value = user;
}

// D11 §7.1 — the frontend hiding layer. The backend is the security boundary;
// this only decides whether to render an affordance, never whether an action
// is allowed (Layer 2, the 403 response, is what actually enforces it).
export function hasPermission(code: string): boolean {
  return currentUser.value?.permissions.includes(code) ?? false;
}
