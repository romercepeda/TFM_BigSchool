import { BaseComponent } from '../components/common/base-component.js';
import { t, loadLocale } from '../i18n/i18n.js';
import { updateLanguage } from '../api/auth.js';
import { currentUser } from '../state/auth-state.js';
import { currentLanguage } from '../state/language-state.js';
import { navigate } from '../router/router.js';

export class SettingsScreen extends BaseComponent {
  private _saving = false;
  private _saved = false;

  protected render(): string {
    const user = currentUser.value;
    return `
      <style>
        :host { display: block; padding: var(--space-6); max-width: 480px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base); }
        .info { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-4); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .success { color: var(--color-success); font-size: var(--font-size-sm); margin-top: var(--space-2); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <h2>${t('settings.title')}</h2>
      ${user ? `<div class="info">${user.email}</div>` : ''}
      <div class="field">
        <label>${t('settings.language')}</label>
        <select id="lang">
          <option value="es" ${currentLanguage.value === 'es' ? 'selected' : ''}>Español</option>
          <option value="en" ${currentLanguage.value === 'en' ? 'selected' : ''}>English</option>
        </select>
      </div>
      <button class="btn" id="save-btn" ${this._saving ? 'disabled' : ''}>
        ${this._saving ? t('common.saving') : t('common.button.save')}
      </button>
      ${this._saved ? `<div class="success">${t('settings.saved')}</div>` : ''}
      <br />
      <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));
    this.shadow.getElementById('save-btn')?.addEventListener('click', async () => {
      const lang = (this.shadow.getElementById('lang') as HTMLSelectElement).value;
      this._saving = true;
      this.shadow.innerHTML = this.render();
      try {
        await updateLanguage(lang);
        await loadLocale(lang);
        if (currentUser.value) {
          currentUser.value = { ...currentUser.value, preferred_language: lang };
        }
        this._saved = true;
      } finally {
        this._saving = false;
        this.shadow.innerHTML = this.render();
      }
    });
  }
}

customElements.define('pi-settings-screen', SettingsScreen);
