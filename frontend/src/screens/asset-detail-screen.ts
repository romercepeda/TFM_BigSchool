import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import '../components/indicator-card.js';
import { t } from '../i18n/i18n.js';
import { getHolding } from '../api/holdings.js';
import { getHoldingSnapshots, listIndicators } from '../api/indicators.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { Holding, Indicator, IndicatorSnapshot } from '../api/types.js';
import { formatCurrency, formatPercent } from '../utils/format.js';
import { activePortfolio } from '../state/portfolio-state.js';

export class AssetDetailScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _holding: Holding | null = null;
  private _indicators: Indicator[] = [];
  private _snapshots: IndicatorSnapshot[] = [];
  private _loading = true;

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this.shadow.innerHTML = this.render();
    [this._holding, this._indicators, this._snapshots] = await Promise.all([
      getHolding(this._portfolioId, this._holdingId),
      listIndicators(),
      getHoldingSnapshots(this._holdingId),
    ]);
    this._loading = false;
    this.shadow.innerHTML = this.render();
    this._mountCards();
  }

  protected render(): string {
    const h = this._holding;
    const gain = h?.unrealized_gain_loss ?? 0;
    const gainColor = gain >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
    return `
      <style>
        :host { display: block; }
        .info { padding: var(--space-4); }
        .ticker { font-size: var(--font-size-2xl); font-weight: var(--font-weight-bold); }
        .gain { color: ${gainColor}; }
        .actions { display: flex; flex-wrap: wrap; gap: var(--space-2); padding: 0 var(--space-4) var(--space-4); }
        .btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-3);
          border-radius: var(--radius-sm); font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .btn:hover { background: var(--color-bg-surface); }
        h3 { padding: var(--space-3) var(--space-4); font-size: var(--font-size-base); color: var(--color-text-secondary); }
        .indicator-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3);
          padding: 0 var(--space-4) var(--space-4); }
        @media (min-width: 768px) { .indicator-grid { grid-template-columns: repeat(3, 1fr); } }
      </style>
      <pi-header-bar></pi-header-bar>
      ${h ? `
        <div class="info">
          <div class="ticker">${h.ticker}</div>
          <div>${h.name}</div>
          <div>${h.quantity} × ${h.current_price != null ? formatCurrency(h.current_price, activePortfolio.value?.base_currency ?? 'EUR') : '—'}</div>
          <div class="gain">
            ${h.unrealized_gain_loss != null ? formatCurrency(h.unrealized_gain_loss, activePortfolio.value?.base_currency ?? 'EUR') : '—'}
            (${formatPercent(h.unrealized_gain_loss_pct ?? 0)})
          </div>
        </div>
        <div class="actions">
          <button class="btn" id="levels-btn">${t('asset_detail.set_levels')}</button>
          <button class="btn" id="analysis-btn">${t('asset_detail.analysis')}</button>
          <button class="btn" id="history-btn">${t('asset_detail.history')}</button>
          <button class="btn" id="back-btn">${t('common.button.back')}</button>
        </div>
        <h3>${t('asset_detail.indicators')}</h3>
        <div class="indicator-grid" id="indicators-grid">
          ${this._loading ? '' : this._indicators.map(() => '<pi-indicator-card></pi-indicator-card>').join('')}
        </div>
      ` : `<div style="padding:var(--space-8);text-align:center">${t('common.loading')}</div>`}
    `;
  }

  protected afterRender(): void {
    const pid = this._portfolioId, hid = this._holdingId;
    this.shadow.getElementById('levels-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}/assets/${hid}/levels`));
    this.shadow.getElementById('analysis-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}/assets/${hid}/analysis`));
    this.shadow.getElementById('history-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}/assets/${hid}/history`));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}`));
    if (!this._loading) this._mountCards();
  }

  private _mountCards(): void {
    const grid = this.shadow.getElementById('indicators-grid');
    if (!grid) return;
    const cards = grid.querySelectorAll('pi-indicator-card') as NodeListOf<HTMLElement & { indicator: Indicator; snapshot: IndicatorSnapshot | null }>;
    cards.forEach((card, i) => {
      card.indicator = this._indicators[i];
      card.snapshot = this._snapshots.find((s) => s.indicator_code === this._indicators[i].code) ?? null;
    });
  }
}

customElements.define('pi-asset-detail-screen', AssetDetailScreen);
