import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { createDateAlert } from '../api/date-alerts.js';
import { required } from '../utils/validation.js';

export class DateAlertForm extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';

  set portfolioId(value: string) {
    this._portfolioId = value;
  }

  set holdingId(value: string) {
    this._holdingId = value;
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        form { display: flex; flex-direction: column; gap: var(--space-3); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input {
          width: 100%; padding: var(--space-2) var(--space-3);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          font-size: var(--font-size-base);
        }
        input:focus { outline: none; border-color: var(--color-border-focus); }
        .error { color: var(--color-danger); font-size: var(--font-size-xs); }
        button[type=submit] {
          background: var(--color-accent); color: #fff;
          padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm);
          font-weight: var(--font-weight-medium);
        }
        button[type=submit]:hover { background: var(--color-accent-hover); }
      </style>
      <form id="date-alert-form">
        <label>${t('screen.date_alert.date')}
          <input type="date" id="alert-date" required />
        </label>
        <label>${t('screen.date_alert.description')}
          <input type="text" id="description" placeholder="${t('screen.date_alert.description_placeholder')}" />
        </label>
        <div id="error" class="error"></div>
        <button type="submit">${t('common.button.save')}</button>
      </form>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('date-alert-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const alertDate = (this.shadow.getElementById('alert-date') as HTMLInputElement).value;
      const description = (this.shadow.getElementById('description') as HTMLInputElement).value;
      const errEl = this.shadow.getElementById('error')!;

      const err = required(alertDate) ?? required(description);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';

      try {
        await createDateAlert(this._portfolioId, this._holdingId, {
          alert_date: alertDate,
          description,
        });
        this.dispatchEvent(new CustomEvent('date-alert-created', { bubbles: true, composed: true }));
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }
}

customElements.define('pi-date-alert-form', DateAlertForm);
