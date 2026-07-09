import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { getPortfolioAlerts } from '../api/portfolios.js';
import { deletePriceLevel, markAlertSeen } from '../api/price-levels.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { PortfolioAlertItem } from '../api/types.js';
import { formatCurrency, formatDateTime, formatPercent } from '../utils/format.js';

export class AlertsScreen extends BaseComponent {
  private _portfolioId = '';
  private _touched: PortfolioAlertItem[] = [];
  private _nearCrossing: PortfolioAlertItem[] = [];
  private _loading = true;
  private _error = '';

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this.shadow.innerHTML = this.render();
    try {
      const data = await getPortfolioAlerts(this._portfolioId);
      this._touched = data.touched;
      this._nearCrossing = data.near_crossing;
    } catch (ex) {
      this._error = (ex as Error).message;
    }
    this._loading = false;
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 640px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        h3 { font-size: var(--font-size-md); margin: var(--space-5) 0 var(--space-3); }
        .alert { border-left: 4px solid var(--color-warning); padding: var(--space-3) var(--space-4);
          margin-bottom: var(--space-3); background: var(--color-warning-light); border-radius: var(--radius-sm); }
        .alert.near { border-left-color: var(--color-accent); background: var(--color-surface-alt, transparent); cursor: pointer; }
        .alert-price { font-weight: var(--font-weight-semibold); }
        .alert-asset { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .alert-meta  { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: 2px; }
        .dismiss-btn { font-size: var(--font-size-sm); color: var(--color-accent); margin-top: var(--space-2); }
        .mark-read-btn { font-size: var(--font-size-sm); color: var(--color-accent); margin-top: var(--space-2); margin-right: var(--space-3); }
        .read-label { font-size: var(--font-size-sm); color: var(--color-text-muted); margin-top: var(--space-2); margin-right: var(--space-3); }
        .unread-dot { display: inline-block; width: 8px; height: 8px; border-radius: 999px;
          background: var(--color-danger, #d9534f); margin-right: var(--space-2); vertical-align: middle; }
        .empty { color: var(--color-text-muted); text-align: center; padding: var(--space-8); }
        .error { color: var(--color-danger, red); text-align: center; padding: var(--space-4); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <div class="page">
        <h2>${t('alerts.title')}</h2>
        ${this._loading ? `<div class="empty">${t('alerts.loading')}</div>` : ''}
        ${this._error ? `<div class="error">${t('alerts.error')}</div>` : ''}
        ${!this._loading && !this._error ? this._renderContent() : ''}
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
      </div>
    `;
  }

  private _renderContent(): string {
    if (this._touched.length === 0 && this._nearCrossing.length === 0) {
      return `<div class="empty">${t('alerts.empty')}</div>`;
    }
    return `
      ${this._touched.length === 0 ? '' : this._touched.map((l) => `
        <div class="alert">
          <div class="alert-asset">${l.alert_seen_at === null ? '<span class="unread-dot"></span>' : ''}${l.asset_ticker} — ${l.asset_name}</div>
          <div class="alert-price">${formatCurrency(l.target_price, l.asset_quote_currency)} ${t('screen.price_level.direction.' + l.direction)}</div>
          ${l.note ? `<div class="alert-meta">${l.note}</div>` : ''}
          ${l.touched_at ? `<div class="alert-meta">${formatDateTime(l.touched_at)}</div>` : ''}
          ${l.alert_seen_at === null
            ? `<button class="mark-read-btn" data-hid="${l.holding_id}" data-lid="${l.id}">${t('alerts.mark_read')}</button>`
            : `<span class="read-label">${t('alerts.read')}</span>`}
          <button class="dismiss-btn" data-hid="${l.holding_id}" data-lid="${l.id}">${t('alerts.dismiss')}</button>
        </div>
      `).join('')}
      ${this._nearCrossing.length === 0 ? '' : `
        <h3>${t('alerts.near_crossing.title')}</h3>
        ${this._nearCrossing.map((l) => `
          <div class="alert near" data-pid="${this._portfolioId}" data-hid="${l.holding_id}" data-nav="1">
            <div class="alert-asset">${l.asset_ticker} — ${l.asset_name}</div>
            <div class="alert-price">${formatCurrency(l.target_price, l.asset_quote_currency)} ${t('screen.price_level.direction.' + l.direction)}</div>
            <div class="alert-meta">${t('alerts.gap_pct', {
              pct: formatPercent((l.gap_pct ?? 0) * 100, 1),
              price: formatCurrency(l.current_price ?? 0, l.asset_quote_currency),
            })}</div>
          </div>
        `).join('')}
      `}
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/app/portfolios/${this._portfolioId}`));
    this.shadow.querySelectorAll('.dismiss-btn').forEach((btn) => {
      btn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const el = btn as HTMLElement;
        await deletePriceLevel(this._portfolioId, el.dataset['hid']!, el.dataset['lid']!);
        void this._load();
      });
    });
    this.shadow.querySelectorAll('.mark-read-btn').forEach((btn) => {
      btn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const el = btn as HTMLElement;
        await markAlertSeen(this._portfolioId, el.dataset['hid']!, el.dataset['lid']!);
        void this._load();
      });
    });
    this.shadow.querySelectorAll('.alert.near').forEach((el) => {
      el.addEventListener('click', () => {
        const target = el as HTMLElement;
        navigate(`/app/portfolios/${target.dataset['pid']}/assets/${target.dataset['hid']}`);
      });
    });
  }
}

customElements.define('pi-alerts-screen', AlertsScreen);
