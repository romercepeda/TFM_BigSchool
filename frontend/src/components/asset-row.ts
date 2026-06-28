import { BaseComponent } from './common/base-component.js';
import { navigate } from '../router/router.js';
import type { Holding } from '../api/types.js';

export class AssetRow extends BaseComponent {
  private _holding: Holding | null = null;
  private _portfolioId = '';

  set holding(value: Holding) {
    this._holding = value;
    if (this.shadow) this.shadow.innerHTML = this.render();
  }

  set portfolioId(value: string) {
    this._portfolioId = value;
  }

  protected render(): string {
    const h = this._holding;
    if (!h) return '<style>:host{display:block}</style>';
    return `
      <style>
        :host { display: block; }
        .row {
          display: flex; align-items: center; justify-content: space-between;
          padding: var(--space-3) var(--space-4);
          border-bottom: 1px solid var(--color-border);
          cursor: pointer; transition: background 0.15s;
        }
        .row:hover { background: var(--color-bg-surface); }
        .left { display: flex; flex-direction: column; gap: 2px; }
        .ticker { font-weight: var(--font-weight-semibold); }
        .name   { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .right  { text-align: right; }
        .price  { font-weight: var(--font-weight-medium); }
        .qty    { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
      </style>
      <div class="row" id="row">
        <div class="left">
          <span class="ticker">${h.asset.ticker}</span>
          <span class="name">${h.asset.name}</span>
        </div>
        <div class="right">
          <div class="price">${Number(h.aggregates.avg_purchase_price_quote).toFixed(2)} ${h.asset.quote_currency}</div>
          <div class="qty">${Number(h.aggregates.quantity_held).toLocaleString()}</div>
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('row')?.addEventListener('click', () => {
      if (this._holding && this._portfolioId) {
        navigate(`/portfolios/${this._portfolioId}/assets/${this._holding.id}`);
      }
    });
  }
}

customElements.define('pi-asset-row', AssetRow);
