import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { formatCurrency, formatPercent } from '../utils/format.js';
import type { PortfolioKpis } from '../api/types.js';

export class KpiStrip extends BaseComponent {
  private _kpis: PortfolioKpis | null = null;

  set kpis(value: PortfolioKpis | null) {
    this._kpis = value;
    if (this.shadow) this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    const k = this._kpis;
    if (!k) return '<style>:host{display:block}</style><div></div>';

    const gainColor = k.total_gain_loss >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
    return `
      <style>
        :host { display: block; }
        .strip {
          display: flex; gap: var(--space-4); flex-wrap: wrap;
          padding: var(--space-3) var(--space-4);
          background: var(--color-bg-secondary);
          border-bottom: 1px solid var(--color-border);
        }
        .kpi { display: flex; flex-direction: column; gap: 2px; }
        .label { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .value { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); }
      </style>
      <div class="strip">
        <div class="kpi">
          <span class="label">${t('kpi.invested')}</span>
          <span class="value">${formatCurrency(k.total_invested, k.base_currency)}</span>
        </div>
        <div class="kpi">
          <span class="label">${t('kpi.current_value')}</span>
          <span class="value">${formatCurrency(k.current_value, k.base_currency)}</span>
        </div>
        <div class="kpi">
          <span class="label">${t('kpi.gain_loss')}</span>
          <span class="value" style="color:${gainColor}">
            ${formatCurrency(k.total_gain_loss, k.base_currency)}
            (${formatPercent(k.total_gain_loss_pct)})
          </span>
        </div>
        <div class="kpi">
          <span class="label">${t('kpi.unrealized')}</span>
          <span class="value">${formatCurrency(k.unrealized_gain_loss, k.base_currency)}</span>
        </div>
        <div class="kpi">
          <span class="label">${t('kpi.realized')}</span>
          <span class="value">${formatCurrency(k.realized_gain_loss, k.base_currency)}</span>
        </div>
      </div>
    `;
  }
}

customElements.define('pi-kpi-strip', KpiStrip);
