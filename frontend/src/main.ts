// App bootstrap — Spec D10 §3.
// Registers all custom elements, initialises i18n, and wires the router.

import './components/common/base-component.js';
import './components/header-bar.js';
import './components/kpi-strip.js';
import './components/asset-row.js';
import './components/indicator-card.js';
import './components/price-level-form.js';
import './components/pdf-uploader.js';

import './screens/login-screen.js';
import './screens/portfolios-screen.js';
import './screens/create-portfolio-screen.js';
import './screens/dashboard-screen.js';
import './screens/add-asset-screen.js';
import './screens/asset-detail-screen.js';
import './screens/set-levels-screen.js';
import './screens/analysis-screen.js';
import './screens/history-screen.js';
import './screens/alerts-screen.js';
import './screens/settings-screen.js';

import { loadLocale } from './i18n/i18n.js';
import { onRouteChange, resolveRoute, replace } from './router/router.js';

const appEl = document.getElementById('app')!;

function renderCurrentRoute(): void {
  const { screen, params } = resolveRoute();
  const el = document.createElement(screen) as HTMLElement & { params?: unknown };
  if (params && Object.keys(params).length > 0) el.params = params;
  appEl.replaceChildren(el);
}

async function bootstrap(): Promise<void> {
  await loadLocale(navigator.language.startsWith('en') ? 'en' : 'es');

  if (location.pathname === '/' || location.pathname === '') {
    replace('/login');
  }

  onRouteChange(renderCurrentRoute);
  renderCurrentRoute();
}

void bootstrap();
