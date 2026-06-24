import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { createPortfolio } from '../api/portfolios.js';
import { navigate } from '../router/router.js';
import { required, maxLength } from '../utils/validation.js';

const CURRENCIES = ['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD'];

export class CreatePortfolioScreen extends BaseComponent {
  protected render(): string {
    return `
      <style>
        :host { display: block; max-width: 480px; margin: 0 auto; padding: var(--space-6); }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input, select {
          padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base);
        }
        input:focus, select:focus { outline: none; border-color: var(--color-border-focus); }
        .actions { display: flex; gap: var(--space-3); margin-top: var(--space-4); }
        .btn-primary { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn-secondary { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); }
      </style>
      <h2>${t('create_portfolio.title')}</h2>
      <div class="field">
        <label>${t('create_portfolio.name')}</label>
        <input type="text" id="name" maxlength="60" />
      </div>
      <div class="field">
        <label>${t('create_portfolio.currency')}</label>
        <select id="currency">
          ${CURRENCIES.map((c) => `<option value="${c}">${c}</option>`).join('')}
        </select>
      </div>
      <div id="error" class="error"></div>
      <div class="actions">
        <button class="btn-primary" id="submit-btn">${t('common.button.create')}</button>
        <button class="btn-secondary" id="back-btn">${t('common.button.cancel')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));
    this.shadow.getElementById('submit-btn')?.addEventListener('click', async () => {
      const name = (this.shadow.getElementById('name') as HTMLInputElement).value;
      const currency = (this.shadow.getElementById('currency') as HTMLSelectElement).value;
      const errEl = this.shadow.getElementById('error')!;
      const err = required(name) ?? maxLength(name, 60);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';
      try {
        const p = await createPortfolio({ name, base_currency: currency });
        navigate(`/portfolios/${p.id}`);
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }
}

customElements.define('pi-create-portfolio-screen', CreatePortfolioScreen);
