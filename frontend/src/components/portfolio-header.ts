// portfolioHeader block — Changeset C08 §7, completed by Spec D13 §8 / C20 §7.
// Four tiles (Valor Total, Invertido, P&L Latente, P&L Realizado) + the
// 30-day trend sparkline. C08 §11.1 deferred the P&L Realizado tile to D13;
// that deferral is now closed.

import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { getPortfolioSummary } from '../api/portfolios.js';
import { formatCurrency, formatPercent } from '../utils/format.js';
import type { PortfolioSummary, TrendPoint } from '../api/types.js';
import './portfolio-trend-sparkline.js';

export class PortfolioHeader extends BaseComponent {
  private _portfolioId = '';
  private _summary: PortfolioSummary | null = null;
  private _loading = true;
  private _error = false;

  set portfolioId(value: string) {
    if (value === this._portfolioId) return;
    this._portfolioId = value;
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = false;
    this._rerender();
    try {
      this._summary = await getPortfolioSummary(this._portfolioId);
    } catch {
      this._error = true;
    }
    this._loading = false;
    this._rerender();
  }

  private _rerender(): void {
    if (!this.shadow) return;
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; margin-bottom: var(--space-6); }
        .header {
          display: flex; gap: var(--space-4); flex-wrap: wrap;
          padding: var(--space-4);
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border); border-radius: var(--radius-md);
        }
        @media (max-width: 639px) { .header { flex-direction: column; } }
        .tile { display: flex; flex-direction: column; gap: 2px; min-width: 120px; flex: 1; }
        .label { font-size: var(--font-size-xs); color: var(--color-text-muted);
          text-transform: uppercase; letter-spacing: 0.05em; }
        .value {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold);
          color: var(--color-text-primary);
        }
        .delta {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-sm);
        }
        .delta.positive, .value.positive { color: var(--color-success); }
        .delta.negative, .value.negative { color: var(--color-danger); }
        .delta.neutral, .value.neutral { color: var(--color-text-secondary); }
        .chart-tile { min-width: 130px; justify-content: center; }
        .skeleton {
          height: 44px; border-radius: var(--radius-sm);
          background: linear-gradient(90deg, var(--color-bg-surface) 25%, var(--color-border) 50%, var(--color-bg-surface) 75%);
          background-size: 200% 100%; animation: pi-shimmer 1.2s ease-in-out infinite;
        }
        @keyframes pi-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .error-tile {
          display: flex; align-items: center; gap: var(--space-3);
          color: var(--color-danger); font-size: var(--font-size-sm);
        }
        .retry-btn {
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          padding: 2px var(--space-3); font-size: var(--font-size-sm); color: var(--color-text-secondary);
        }
        .retry-btn:hover { background: var(--color-bg-surface); }
      </style>
      <div class="header">
        ${this._loading
          ? this._renderSkeleton()
          : this._error
            ? this._renderError()
            : this._renderContent()}
      </div>
    `;
  }

  private _renderSkeleton(): string {
    return `
      <div class="tile skeleton"></div>
      <div class="tile skeleton"></div>
      <div class="tile skeleton"></div>
      <div class="tile skeleton"></div>
      <div class="tile skeleton"></div>
      <div class="tile skeleton"></div>
    `;
  }

  private _renderError(): string {
    return `
      <div class="error-tile">
        <span>${t('portfolio_header.loading_error')}</span>
        <button class="retry-btn" id="retry-btn">${t('portfolio_header.retry')}</button>
      </div>
    `;
  }

  private _renderContent(): string {
    const s = this._summary;
    if (!s) return '';
    const currency = s.base_currency;
    const totalValue = Number(s.total_value);
    const invested = Number(s.total_invested);
    const pnl = Number(s.unrealized_pnl);
    const pnlPct = Number(s.unrealized_pnl_pct);
    const deltaClass = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : 'neutral';
    const sign = pnl > 0 ? '+' : '';

    const realizedPnl = Number(s.realized_pnl);
    const realizedClass = realizedPnl > 0 ? 'positive' : realizedPnl < 0 ? 'negative' : 'neutral';

    const dividendIncome = Number(s.dividend_income);

    return `
      <div class="tile">
        <span class="label">${t('portfolio_header.total_value')}</span>
        <span class="value">${formatCurrency(totalValue, currency)}</span>
        <span class="delta ${deltaClass}">
          ${sign}${formatCurrency(pnl, currency)} (${sign}${formatPercent(pnlPct * 100)})
        </span>
      </div>
      <div class="tile">
        <span class="label">${t('portfolio_header.invested')}</span>
        <span class="value">${formatCurrency(invested, currency)}</span>
      </div>
      <div class="tile">
        <span class="label">${t('portfolio_header.unrealized_pnl')}</span>
        <span class="value ${deltaClass}">${formatCurrency(pnl, currency)}</span>
      </div>
      <div class="tile">
        <span class="label">${t('portfolio_header.realized_pnl')}</span>
        <span class="value ${realizedClass}">${formatCurrency(realizedPnl, currency)}</span>
      </div>
      <div class="tile">
        <span class="label">${t('portfolio_header.dividend_income')}</span>
        <span class="value">${formatCurrency(dividendIncome, currency)}</span>
      </div>
      <div class="tile chart-tile">
        <span class="label">${t('portfolio_header.trend_30d')}</span>
        <pi-portfolio-trend-sparkline id="sparkline"></pi-portfolio-trend-sparkline>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('retry-btn')?.addEventListener('click', () => void this._load());

    if (this._summary) {
      const sparkline = this.shadow.getElementById('sparkline') as
        (HTMLElement & { points: TrendPoint[]; currency: string }) | null;
      if (sparkline) {
        sparkline.points = this._summary.trend_30d;
        sparkline.currency = this._summary.base_currency;
      }
    }
  }
}

customElements.define('pi-portfolio-header', PortfolioHeader);
