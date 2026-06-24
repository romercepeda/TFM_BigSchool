import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { addAsset } from '../api/holdings.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import { required, positiveNumber } from '../utils/validation.js';

export class AddAssetScreen extends BaseComponent {
  private _portfolioId = '';

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; max-width: 480px; margin: 0 auto; padding: var(--space-6); }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base); }
        input:focus { outline: none; border-color: var(--color-border-focus); }
        .actions { display: flex; gap: var(--space-3); margin-top: var(--space-4); }
        .btn-primary { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn-secondary { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); }
      </style>
      <h2>${t('add_asset.title')}</h2>
      <div class="field"><label>${t('add_asset.ticker')}</label><input type="text" id="ticker" /></div>
      <div class="field"><label>${t('add_asset.quantity')}</label><input type="number" id="quantity" step="0.0001" /></div>
      <div class="field"><label>${t('add_asset.cost')}</label><input type="number" id="cost" step="0.01" /></div>
      <div class="field"><label>${t('add_asset.date')}</label><input type="date" id="date" /></div>
      <div id="error" class="error"></div>
      <div class="actions">
        <button class="btn-primary" id="submit-btn">${t('common.button.add')}</button>
        <button class="btn-secondary" id="back-btn">${t('common.button.cancel')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}`));
    this.shadow.getElementById('submit-btn')?.addEventListener('click', async () => {
      const ticker = (this.shadow.getElementById('ticker') as HTMLInputElement).value.toUpperCase();
      const qty    = (this.shadow.getElementById('quantity') as HTMLInputElement).value;
      const cost   = (this.shadow.getElementById('cost') as HTMLInputElement).value;
      const date   = (this.shadow.getElementById('date') as HTMLInputElement).value;
      const errEl  = this.shadow.getElementById('error')!;
      const err = required(ticker) ?? required(date) ?? positiveNumber(qty) ?? positiveNumber(cost);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';
      try {
        await addAsset(this._portfolioId, {
          ticker, quantity: Number(qty), cost_per_unit: Number(cost), acquired_at: date,
        });
        navigate(`/portfolios/${this._portfolioId}`);
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }
}

customElements.define('pi-add-asset-screen', AddAssetScreen);
