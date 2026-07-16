import { BaseComponent } from './common/base-component.js';
import { navigate } from '../router/router.js';
import { t } from '../i18n/i18n.js';
import { formatCurrency, formatNumber, formatPercent } from '../utils/format.js';
import type { Holding, HoldingPnl } from '../api/types.js';

export class AssetRow extends BaseComponent {
  private _holding: Holding | null = null;
  private _portfolioId = '';
  private _pnl: HoldingPnl | null = null;
  private _baseCurrency = '';

  set holding(value: Holding) {
    this._holding = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this.afterRender(); }
  }

  set portfolioId(value: string) {
    this._portfolioId = value;
  }

  // Spec D13 §10 — per-holding P&L summary line.
  set pnl(value: HoldingPnl) {
    this._pnl = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this.afterRender(); }
  }

  set baseCurrency(value: string) {
    this._baseCurrency = value;
  }

  private _renderPnlSummary(): string {
    const p = this._pnl;
    if (!p) return '';
    const activeUnits = Number(p.active_units);

    if (activeUnits <= 0) {
      const realized = Number(p.realized_pnl);
      const cls = realized > 0 ? 'positive' : realized < 0 ? 'negative' : '';
      const sign = realized >= 0 ? '+' : '';
      const arrow = realized > 0 ? '▲' : realized < 0 ? '▼' : '';
      return `
        <div class="pnl-summary">
          <span>${t('screen.dashboard.sold')}</span>
          <span class="${cls}">${t('screen.dashboard.realized_pnl_row', {
            amount: `${sign}${formatCurrency(realized, this._baseCurrency)}`,
          })} ${arrow}</span>
        </div>
      `;
    }

    const totalPnl = Number(p.total_pnl);
    const cls = totalPnl > 0 ? 'positive' : totalPnl < 0 ? 'negative' : '';
    const sign = totalPnl >= 0 ? '+' : '';
    const arrow = totalPnl > 0 ? '▲' : totalPnl < 0 ? '▼' : '';
    return `
      <div class="pnl-summary">
        <span>${formatNumber(activeUnits, { maximumFractionDigits: 8 })} ${t('screen.dashboard.units')}</span>
        <span>·</span>
        <span>${t('screen.portfolios.invested', { amount: formatCurrency(Number(p.invested), this._baseCurrency) })}</span>
        <span>·</span>
        <span class="${cls}">${sign}${formatCurrency(totalPnl, this._baseCurrency)} (${sign}${formatPercent(Number(p.total_pnl_pct) * 100)}) ${arrow}</span>
      </div>
    `;
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
        .market { font-size: var(--font-size-xs); color: var(--color-text-muted); font-weight: normal; }
        .name   { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .right  { text-align: right; }
        .price  {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-weight: var(--font-weight-medium);
        }
        .qty    {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-sm); color: var(--color-text-secondary);
        }
        .pnl-summary { font-size: var(--font-size-xs); color: var(--color-text-secondary);
          margin-top: 2px; display: flex; gap: 6px; flex-wrap: wrap; }
        .pnl-summary .positive { color: var(--color-success); }
        .pnl-summary .negative { color: var(--color-danger); }
      </style>
      <div class="row" id="row">
        <div class="left">
          <span class="ticker">
            ${h.asset.ticker}
            ${h.asset.market ? `<span class="market">${h.asset.market}</span>` : ''}
          </span>
          <span class="name">${h.asset.name}</span>
          ${this._renderPnlSummary()}
        </div>
        <div class="right">
          <div class="price">${Number(h.aggregates.avg_purchase_price_quote).toFixed(2)} ${h.asset.quote_currency}</div>
          <div class="qty">${Number(h.aggregates.quantity_held).toLocaleString()} ${t('screen.dashboard.units')}</div>
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('row')?.addEventListener('click', () => {
      if (this._holding && this._portfolioId) {
        navigate(`/app/portfolios/${this._portfolioId}/assets/${this._holding.id}`);
      }
    });
  }
}

customElements.define('pi-asset-row', AssetRow);
