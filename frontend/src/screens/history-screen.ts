import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listLots, listSales } from '../api/holdings.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { Lot, Sale } from '../api/types.js';
import { formatCurrency, formatDate } from '../utils/format.js';

export class HistoryScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _lots: Lot[] = [];
  private _sales: Sale[] = [];

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    [this._lots, this._sales] = await Promise.all([
      listLots(this._portfolioId, this._holdingId),
      listSales(this._portfolioId, this._holdingId),
    ]);
    this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 640px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        h3 { font-size: var(--font-size-base); color: var(--color-text-secondary); margin: var(--space-6) 0 var(--space-3); }
        table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
        th { text-align: left; color: var(--color-text-muted); padding: var(--space-2); border-bottom: 2px solid var(--color-border); }
        td { padding: var(--space-2); border-bottom: 1px solid var(--color-border); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-6); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <h2>${t('history.title')}</h2>
        <h3>${t('history.lots')}</h3>
        <table>
          <thead><tr><th>${t('history.date')}</th><th>${t('history.qty')}</th><th>${t('history.cost')}</th></tr></thead>
          <tbody>
            ${this._lots.map((l) => `
              <tr>
                <td>${formatDate(l.purchase_date + 'T12:00:00')}</td>
                <td>${l.quantity}</td>
                <td>${formatCurrency(Number(l.unit_price), 'EUR')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
        <h3>${t('history.sales')}</h3>
        <table>
          <thead><tr><th>${t('history.date')}</th><th>${t('history.qty')}</th><th>${t('history.price')}</th></tr></thead>
          <tbody>
            ${this._sales.map((s) => `
              <tr>
                <td>${formatDate(s.sale_date + 'T12:00:00')}</td>
                <td>${s.quantity}</td>
                <td>${formatCurrency(Number(s.unit_price), 'EUR')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/assets/${this._holdingId}`));
  }
}

customElements.define('pi-history-screen', HistoryScreen);
