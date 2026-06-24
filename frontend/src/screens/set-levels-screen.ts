import { BaseComponent } from '../components/common/base-component.js';
import '../components/price-level-form.js';
import { t } from '../i18n/i18n.js';
import { listPriceLevels, deletePriceLevel } from '../api/price-levels.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { PriceLevel } from '../api/types.js';
import { formatCurrency } from '../utils/format.js';

export class SetLevelsScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _levels: PriceLevel[] = [];

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._levels = await listPriceLevels(this._holdingId);
    this.shadow.innerHTML = this.render();
    this._wire();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; padding: var(--space-6); max-width: 560px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        h3 { font-size: var(--font-size-base); color: var(--color-text-secondary); margin: var(--space-6) 0 var(--space-3); }
        .level { display: flex; align-items: center; justify-content: space-between;
          padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          margin-bottom: var(--space-2); }
        .del-btn { color: var(--color-danger); font-size: var(--font-size-sm); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <h2>${t('set_levels.title')}</h2>
      <pi-price-level-form id="form"></pi-price-level-form>
      <h3>${t('set_levels.existing')}</h3>
      <div id="levels-list">
        ${this._levels.map((l) => `
          <div class="level">
            <span>${formatCurrency(l.price, 'EUR')} ${t('price_level.direction.' + l.direction)} ${l.label ? `— ${l.label}` : ''}</span>
            <button class="del-btn" data-id="${l.id}">${t('common.button.delete')}</button>
          </div>
        `).join('')}
      </div>
      <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
    `;
  }

  protected afterRender(): void {
    this._wire();
  }

  private _wire(): void {
    const form = this.shadow.getElementById('form') as HTMLElement & { holdingId: string };
    if (form) form.holdingId = this._holdingId;
    this.shadow.getElementById('form')?.addEventListener('level-created', () => void this._load());
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/assets/${this._holdingId}`));
    this.shadow.querySelectorAll('.del-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await deletePriceLevel(this._holdingId, (btn as HTMLElement).dataset['id']!);
        void this._load();
      });
    });
  }
}

customElements.define('pi-set-levels-screen', SetLevelsScreen);
