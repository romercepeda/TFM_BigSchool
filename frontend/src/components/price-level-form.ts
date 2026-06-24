import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { createPriceLevel } from '../api/price-levels.js';
import { required, positiveNumber } from '../utils/validation.js';

export class PriceLevelForm extends BaseComponent {
  private _holdingId = '';

  set holdingId(value: string) {
    this._holdingId = value;
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
        <label>${t('price_level.form.price')}
          <input type="number" id="price" step="0.01" placeholder="0.00" required />
        </label>
        <label>${t('price_level.form.direction')}
          <select id="direction">
            <option value="above">${t('price_level.direction.above')}</option>
            <option value="below">${t('price_level.direction.below')}</option>
          </select>
        </label>
        <label>${t('price_level.form.label')}
          <input type="text" id="label-field" />
        </label>
        <div id="error" class="error"></div>
        <button type="submit">${t('common.button.save')}</button>
      </form>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('level-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const price = (this.shadow.getElementById('price') as HTMLInputElement).value;
      const direction = (this.shadow.getElementById('direction') as HTMLSelectElement).value as 'above' | 'below';
      const label = (this.shadow.getElementById('label-field') as HTMLInputElement).value;
      const errEl = this.shadow.getElementById('error')!;

      const err = required(price) ?? positiveNumber(price);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';

      try {
        await createPriceLevel(this._holdingId, { price: Number(price), direction, label: label || undefined });
        this.dispatchEvent(new CustomEvent('level-created', { bubbles: true, composed: true }));
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }
}

customElements.define('pi-price-level-form', PriceLevelForm);
