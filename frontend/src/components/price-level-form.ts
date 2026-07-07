import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { createPriceLevels } from '../api/price-levels.js';
import type { PriceLevelDirection } from '../api/types.js';
import { required, positiveNumber } from '../utils/validation.js';

export class PriceLevelForm extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _currentPrice: number | null = null;

  set portfolioId(value: string) {
    this._portfolioId = value;
  }

  set holdingId(value: string) {
    this._holdingId = value;
  }

  set currentPrice(value: number | null) {
    this._currentPrice = value;
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        form { display: flex; flex-direction: column; gap: var(--space-3); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input, select {
          width: 100%; padding: var(--space-2) var(--space-3);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          font-size: var(--font-size-base);
        }
        input:focus, select:focus { outline: none; border-color: var(--color-border-focus); }
        .error { color: var(--color-danger); font-size: var(--font-size-xs); }
        button[type=submit] {
          background: var(--color-accent); color: #fff;
          padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm);
          font-weight: var(--font-weight-medium);
        }
        button[type=submit]:hover { background: var(--color-accent-hover); }
      </style>
      <form id="level-form">
        <label>${t('screen.price_level.price')}
          <input type="number" id="target-price" step="0.01" placeholder="0.00" required />
        </label>
        <label>${t('screen.price_level.direction_label')}
          <select id="direction">
            <option value="buy">${t('screen.price_level.direction.buy')}</option>
            <option value="sell">${t('screen.price_level.direction.sell')}</option>
          </select>
        </label>
        <label>${t('screen.price_level.notes')}
          <input type="text" id="note" />
        </label>
        <div id="error" class="error"></div>
        <button type="submit">${t('common.button.save')}</button>
      </form>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('level-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const targetPrice = (this.shadow.getElementById('target-price') as HTMLInputElement).value;
      const direction = (this.shadow.getElementById('direction') as HTMLSelectElement).value as PriceLevelDirection;
      const note = (this.shadow.getElementById('note') as HTMLInputElement).value;
      const errEl = this.shadow.getElementById('error')!;

      const err = required(targetPrice) ?? positiveNumber(targetPrice);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';

      try {
        await createPriceLevels(this._portfolioId, this._holdingId, {
          levels: [{ direction, target_price: Number(targetPrice), note: note || undefined }],
          asset_price_at_event: this._currentPrice ?? undefined,
        });
        this.dispatchEvent(new CustomEvent('level-created', { bubbles: true, composed: true }));
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }
}

customElements.define('pi-price-level-form', PriceLevelForm);
