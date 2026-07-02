// Hand-written History API router — Spec D10 §6 (~50 lines).

import { currentUser, hasPermission } from '../state/auth-state.js';
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

const CHANGE_PASSWORD_PATH = '/settings/change-password';

export function resolveRoute(): { screen: string; params: RouteParams } {
  const path = currentPath();
  const match = matchRoute(path);
  if (!match) return { screen: 'not-found', params: {} };

  if (match.authRequired && currentUser.value === null) {
    _redirectAfterLogin = path;
    replace('/login');
    return { screen: 'pi-login-screen', params: {} };
  }

  // D11 §7.4 / §6.4: a user who must change their password cannot navigate
  // anywhere else until they do, even by typing a URL directly.
  if (
    match.authRequired &&
    currentUser.value?.must_change_password &&
    path !== CHANGE_PASSWORD_PATH
  ) {
    replace(CHANGE_PASSWORD_PATH);
    return { screen: 'pi-change-password-screen', params: {} };
  }

  // D11 §7.5: typing a URL you lack permission for shows a full-screen
  // placeholder in place, without leaking anything via a redirect/history entry.
  if (match.requiredPermission && !hasPermission(match.requiredPermission)) {
    return { screen: 'pi-permission-denied-screen', params: {} };
  }

  return { screen: match.screen, params: match.params };
}

export function consumeRedirectAfterLogin(): string | null {
  const path = _redirectAfterLogin;
  _redirectAfterLogin = null;
  return path;
}

window.addEventListener('popstate', _dispatch);
