import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { dismissAlert } from '../api/price-levels.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { PriceLevel } from '../api/types.js';
import { formatCurrency, formatDateTime } from '../utils/format.js';

export class AlertsScreen extends BaseComponent {
  private _portfolioId = '';
  private _levels: PriceLevel[] = [];

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    // holdingId not in the route — alerts are portfolio-wide (conceptually)
    // For now we show all triggered levels across all holdings.
    // The backend filters by portfolio via /portfolios/:id/alerts if available,
    // otherwise this screen is accessed per-holding context.
    void this._load();
  }

  private async _load(): Promise<void> {
    // Reuse holding id stored in route if the user navigated here from a holding.
    this._levels = [];
    this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    const triggered = this._levels.filter((l) => l.alert_status === 'triggered');
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 640px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        .alert { border-left: 4px solid var(--color-warning); padding: var(--space-3) var(--space-4);
          margin-bottom: var(--space-3); background: var(--color-warning-light); border-radius: var(--radius-sm); }
        .alert-price { font-weight: var(--font-weight-semibold); }
        .alert-meta  { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: 2px; }
        .dismiss-btn { font-size: var(--font-size-sm); color: var(--color-accent); margin-top: var(--space-2); }
        .empty { color: var(--color-text-muted); text-align: center; padding: var(--space-8); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <div class="page">
        <h2>${t('alerts.title')}</h2>
        ${triggered.length === 0
          ? `<div class="empty">${t('alerts.empty')}</div>`
          : triggered.map((l) => `
            <div class="alert">
              <div class="alert-price">${formatCurrency(l.price, 'EUR')} ${t('price_level.direction.' + l.direction)}</div>
              ${l.label ? `<div class="alert-meta">${l.label}</div>` : ''}
              ${l.triggered_at ? `<div class="alert-meta">${formatDateTime(l.triggered_at)}</div>` : ''}
              <button class="dismiss-btn" data-hid="${l.holding_id}" data-lid="${l.id}">${t('alerts.dismiss')}</button>
            </div>
          `).join('')}
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}`));
    this.shadow.querySelectorAll('.dismiss-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const el = btn as HTMLElement;
        await dismissAlert(el.dataset['hid']!, el.dataset['lid']!);
        void this._load();
      });
    });
  }
}

customElements.define('pi-alerts-screen', AlertsScreen);
