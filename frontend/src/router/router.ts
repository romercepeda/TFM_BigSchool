// Hand-written History API router — Spec D10 §6 (~50 lines).

import { currentUser } from '../state/auth-state.js';
import { matchRoute } from './routes.js';

export type RouteParams = Record<string, string>;

const _subscribers = new Set<() => void>();
let _redirectAfterLogin: string | null = null;

export function navigate(path: string): void {
  history.pushState(null, '', path);
  _dispatch();
}

export function replace(path: string): void {
  history.replaceState(null, '', path);
  _dispatch();
}

function _dispatch(): void {
  _subscribers.forEach((fn) => fn());
}

export function onRouteChange(fn: () => void): () => void {
  _subscribers.add(fn);
  return () => _subscribers.delete(fn);
}

export function currentPath(): string {
  return location.pathname;
}

export function resolveRoute(): { screen: string; params: RouteParams } {
  const path = currentPath();
  const match = matchRoute(path);
  if (!match) return { screen: 'not-found', params: {} };

  if (match.authRequired && currentUser.value === null) {
    _redirectAfterLogin = path;
    replace('/login');
    return { screen: 'pi-login-screen', params: {} };
  }

  return { screen: match.screen, params: match.params };
}

export function consumeRedirectAfterLogin(): string | null {
  const path = _redirectAfterLogin;
  _redirectAfterLogin = null;
  return path;
}

window.addEventListener('popstate', _dispatch);
