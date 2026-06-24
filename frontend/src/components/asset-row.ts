import { BaseComponent } from './common/base-component.js';
import { formatCurrency, formatPercent } from '../utils/format.js';
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
    const gain = h.unrealized_gain_loss ?? 0;
    const gainPct = h.unrealized_gain_loss_pct ?? 0;
    const gainColor = gain >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
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
        .value  { font-weight: var(--font-weight-medium); }
        .gain   { font-size: var(--font-size-sm); }
      </style>
      <div class="row" id="row">
        <div class="left">
          <span class="ticker">${h.ticker}</span>
          <span class="name">${h.name}</span>
        </div>
        <div class="right">
          <div class="value">${h.current_value != null ? formatCurrency(h.current_value, 'EUR') : '—'}</div>
          <div class="gain" style="color:${gainColor}">${formatPercent(gainPct)}</div>
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
