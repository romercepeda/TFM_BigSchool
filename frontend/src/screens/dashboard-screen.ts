import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import '../components/kpi-strip.js';
import '../components/asset-row.js';
import { t } from '../i18n/i18n.js';
import { getPortfolioKpis } from '../api/portfolios.js';
import { listHoldings } from '../api/holdings.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { Holding, PortfolioKpis } from '../api/types.js';

export class DashboardScreen extends BaseComponent {
  private _portfolioId = '';
  private _kpis: PortfolioKpis | null = null;
  private _holdings: Holding[] = [];
  private _loading = true;

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this.shadow.innerHTML = this.render();
    [this._kpis, this._holdings] = await Promise.all([
      getPortfolioKpis(this._portfolioId),
      listHoldings(this._portfolioId),
    ]);
    this._loading = false;
    this.shadow.innerHTML = this.render();
    this._mountComponents();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .actions { display: flex; gap: var(--space-3); padding: var(--space-4); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        h3 { padding: var(--space-3) var(--space-4); font-size: var(--font-size-lg); }
        .loading { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
      </style>
      <pi-header-bar></pi-header-bar>
      <div id="kpi-container"></div>
      <div class="actions">
        <button class="btn" id="add-btn">${t('dashboard.add_asset')}</button>
        <button class="btn-outline" id="alerts-btn">${t('dashboard.alerts')}</button>
        <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
      </div>
      <h3>${t('dashboard.holdings')}</h3>
      ${this._loading
        ? `<div class="loading">${t('common.loading')}</div>`
        : `<div id="holdings-list"></div>`}
    `;
  }

  protected afterRender(): void {
    if (!this._loading) this._mountComponents();
    this.shadow.getElementById('add-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/add-asset`));
    this.shadow.getElementById('alerts-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/alerts`));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));
  }

  private _mountComponents(): void {
    const kpiEl = this.shadow.getElementById('kpi-container');
    if (kpiEl && this._kpis) {
      kpiEl.innerHTML = '<pi-kpi-strip></pi-kpi-strip>';
      const strip = kpiEl.querySelector('pi-kpi-strip') as (HTMLElement & { kpis: PortfolioKpis | null });
      if (strip) strip.kpis = this._kpis;
    }
    const listEl = this.shadow.getElementById('holdings-list');
    if (listEl) {
      listEl.innerHTML = this._holdings.map(() => '<pi-asset-row></pi-asset-row>').join('');
      const rows = listEl.querySelectorAll('pi-asset-row') as NodeListOf<HTMLElement & { holding: Holding; portfolioId: string }>;
      rows.forEach((row, i) => {
        row.holding = this._holdings[i];
        row.portfolioId = this._portfolioId;
      });
    }
  }
}

customElements.define('pi-dashboard-screen', DashboardScreen);
