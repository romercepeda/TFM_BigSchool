import { BaseComponent } from '../components/common/base-component.js';
import '../components/data-providers-editor.js';
import { t, loadLocale } from '../i18n/i18n.js';
import { updateLanguage, logout } from '../api/auth.js';
import { runDailyUpdate } from '../api/market-data.js';
import type { DailyUpdateResult } from '../api/market-data.js';
import { currentUser, clearAuthState, hasPermission } from '../state/auth-state.js';
import { currentLanguage } from '../state/language-state.js';
import { currentTheme, setTheme } from '../state/theme-state.js';
import { stopPolling } from '../state/notification-state.js';
import { THEMES } from '../config/app-config.js';
import type { Theme } from '../config/app-config.js';
import { navigate } from '../router/router.js';

export class SettingsScreen extends BaseComponent {
  private _saving = false;
  private _saved = false;
  private _updating = false;
  private _updateResult: DailyUpdateResult | null = null;
  private _updateError = '';

  protected render(): string {
    const user = currentUser.value;
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 520px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }

        .section { margin-bottom: var(--space-8); }
        .section-title {
          font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary); text-transform: uppercase;
          letter-spacing: 0.05em; margin-bottom: var(--space-4);
          padding-bottom: var(--space-2); border-bottom: 1px solid var(--color-border);
        }

        .info-row { display: flex; align-items: center; gap: var(--space-3);
          font-size: var(--font-size-sm); color: var(--color-text-secondary);
          margin-bottom: var(--space-4); }
        .info-label { color: var(--color-text-muted); min-width: 80px; }
        .info-value { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }

        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        select {
          padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base);
          background: var(--color-bg-primary); color: var(--color-text-primary); width: 100%;
        }
        select:focus { outline: none; border-color: var(--color-border-focus); }

        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover:not(:disabled) { background: var(--color-accent-hover); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover:not(:disabled) { background: var(--color-bg-surface); }
        .btn-outline:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-danger-outline { border: 1px solid var(--color-danger); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-danger); font-size: var(--font-size-sm); }
        .btn-danger-outline:hover { background: var(--color-danger); color: #fff; }

        .feedback { font-size: var(--font-size-sm); margin-top: var(--space-3); }
        .feedback.success { color: var(--color-success); }
        .feedback.error   { color: var(--color-danger); }
        .hint { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: var(--space-1); }

        /* ── Theme picker ── */
        .theme-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
          gap: var(--space-3); margin: var(--space-3) 0;
        }
        .theme-card {
          border: 2px solid var(--color-border); border-radius: var(--radius-md);
          overflow: hidden; cursor: pointer; text-align: center;
          padding-bottom: var(--space-2); background: transparent;
        }
        .theme-card:hover  { border-color: var(--color-accent); }
        .theme-card.active {
          border-color: var(--color-accent);
          box-shadow: 0 0 0 3px var(--color-accent-light);
        }
        .swatch-bar  { height: 10px; }
        .swatch-body { height: 40px; }
        .theme-label {
          font-size: var(--font-size-xs); color: var(--color-text-secondary);
          padding-top: var(--space-1); display: block; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; padding-inline: var(--space-1);
        }
        .theme-card.active .theme-label { color: var(--color-accent); font-weight: var(--font-weight-semibold); }

        /* ── Market data ── */
        .update-desc { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-3); }
        .update-result {
          margin-top: var(--space-3); padding: var(--space-3);
          background: var(--color-bg-secondary); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-sm);
        }
        .result-row { display: flex; justify-content: space-between; padding: var(--space-1) 0; }
        .result-label { color: var(--color-text-secondary); }
        .result-value { font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
        .result-value.warn { color: var(--color-danger); }

        .back-section { padding-top: var(--space-4); border-top: 1px solid var(--color-border); }
      </style>

      <pi-header-bar></pi-header-bar>
      <div class="page">
        <h2>${t('screen.config.title')}</h2>

        <!-- ── Cuenta ──────────────────────────────── -->
        <div class="section">
          <div class="section-title">${t('settings.section.account')}</div>

          ${user ? `<div class="info-row">
            <span class="info-label">Email</span>
            <span class="info-value">${user.email}</span>
          </div>` : ''}

          <div class="field">
            <label>${t('screen.config.language')}</label>
            <select id="lang">
              <option value="es" ${currentLanguage.value === 'es' ? 'selected' : ''}>${t('screen.config.language.es')}</option>
              <option value="en" ${currentLanguage.value === 'en' ? 'selected' : ''}>${t('screen.config.language.en')}</option>
            </select>
          </div>

          <div style="display:flex;gap:var(--space-3);align-items:center;flex-wrap:wrap">
            <button class="btn" id="save-lang-btn" ${this._saving ? 'disabled' : ''}>
              ${this._saving ? t('settings.saving') : t('common.button.save')}
            </button>
            <button class="btn-danger-outline" id="logout-btn">${t('nav.logout')}</button>
          </div>
          ${this._saved ? `<div class="feedback success">✓ ${t('settings.saved')}</div>` : ''}

          ${user ? `<div style="margin-top:var(--space-4);display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap">
            <button class="btn-outline" id="change-password-btn" ${user.auth_provider !== 'password' ? 'disabled' : ''}>
              ${t('settings.change_password.link')}
            </button>
            ${user.auth_provider !== 'password'
              ? `<span class="hint">${user.auth_provider === 'guest' ? t('screen.change_password.provider_guest') : t('screen.change_password.provider_oauth')}</span>`
              : ''}
          </div>` : ''}
        </div>

        <!-- ── Apariencia ───────────────────────────── -->
        <div class="section">
          <div class="section-title">${t('settings.section.appearance')}</div>
          <label>${t('settings.theme')}</label>
          <div class="theme-grid">
            ${THEMES.map((th) => `
              <button
                class="theme-card${currentTheme.value === th.id ? ' active' : ''}"
                data-theme-id="${th.id}"
                title="${t(th.labelKey)}"
              >
                <div class="swatch-bar"  style="background:${th.swatchAccent}"></div>
                <div class="swatch-body" style="background:${th.swatchBg};border-bottom:1px solid ${th.swatchBorder}"></div>
                <span class="theme-label">${t(th.labelKey)}</span>
              </button>
            `).join('')}
          </div>
          <div class="hint">${t('settings.theme.auto_saved')}</div>
        </div>

        <!-- ── Datos de mercado ─────────────────────── -->
        <div class="section">
          <div class="section-title">${t('settings.section.market_data')}</div>
          <div class="update-desc">${t('settings.market_data.desc')}</div>
          <button class="btn-outline" id="update-btn" ${this._updating ? 'disabled' : ''}>
            ${this._updating ? t('settings.market_data.running') : t('settings.market_data.run')}
          </button>

          ${this._updateError
            ? `<div class="feedback error">✗ ${this._updateError}</div>`
            : this._updateResult
              ? `<div class="update-result">
                  <div class="result-row">
                    <span class="result-label">${t('settings.market_data.assets_ok')}</span>
                    <span class="result-value">${this._updateResult.assets_processed}</span>
                  </div>
                  <div class="result-row">
                    <span class="result-label">${t('settings.market_data.assets_failed')}</span>
                    <span class="result-value ${this._updateResult.assets_failed > 0 ? 'warn' : ''}">${this._updateResult.assets_failed}</span>
                  </div>
                  ${this._updateResult.assets_failed > 0
                    ? `<div class="feedback error" style="margin-top:var(--space-2)">${t('settings.market_data.failed_hint')}</div>`
                    : ''}
                  <div class="result-row">
                    <span class="result-label">${t('settings.market_data.indicators')}</span>
                    <span class="result-value">${this._updateResult.indicator_snapshots}</span>
                  </div>
                  <div class="result-row">
                    <span class="result-label">${t('settings.market_data.alerts')}</span>
                    <span class="result-value">${this._updateResult.alerts_triggered}</span>
                  </div>
                </div>`
              : ''}
        </div>

        <!-- ── Proveedores de datos (solo administradores) ─────────────── -->
        ${hasPermission('system.view_config') ? `
          <div class="section">
            <div class="section-title">${t('settings.section.data_providers')}</div>
            <pi-data-providers-editor></pi-data-providers-editor>
          </div>
        ` : ''}

        <!-- ── Navegación ───────────────────────────── -->
        <div class="back-section">
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));

    // Language save
    this.shadow.getElementById('save-lang-btn')?.addEventListener('click', async () => {
      const lang = (this.shadow.getElementById('lang') as HTMLSelectElement).value;
      this._saving = true;
      this._saved = false;
      this.shadow.innerHTML = this.render();
      this.afterRender();
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
        this.afterRender();
      }
    });

    // Change password
    this.shadow.getElementById('change-password-btn')?.addEventListener('click', () =>
      navigate('/settings/change-password'));

    // Logout
    this.shadow.getElementById('logout-btn')?.addEventListener('click', async () => {
      await logout();
      clearAuthState();
      stopPolling();
      navigate('/login');
    });

    // Theme picker — instant switch, no Save button needed
    this.shadow.querySelectorAll<HTMLElement>('.theme-card').forEach((card) => {
      card.addEventListener('click', () => {
        const id = card.dataset['themeId'] as Theme | undefined;
        if (id) {
          setTheme(id);
          this.shadow.innerHTML = this.render();
          this.afterRender();
        }
      });
    });

    // Market data update
    this.shadow.getElementById('update-btn')?.addEventListener('click', async () => {
      this._updating = true;
      this._updateResult = null;
      this._updateError = '';
      this.shadow.innerHTML = this.render();
      this.afterRender();
      try {
        this._updateResult = await runDailyUpdate();
      } catch (ex) {
        this._updateError = (ex as Error).message;
      } finally {
        this._updating = false;
        this.shadow.innerHTML = this.render();
        this.afterRender();
      }
    });
  }
}

customElements.define('pi-settings-screen', SettingsScreen);
