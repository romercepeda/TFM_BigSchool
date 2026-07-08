import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { changePassword } from '../api/auth.js';
import { currentUser, updateCurrentUser } from '../state/auth-state.js';
import { navigate, consumeRedirectAfterLogin } from '../router/router.js';

const MIN_PASSWORD_LENGTH = 12;

interface FormState { currentPassword: string; newPassword: string; confirmPassword: string; }

const emptyForm = (): FormState => ({ currentPassword: '', newPassword: '', confirmPassword: '' });

export class ChangePasswordScreen extends BaseComponent {
  private _error = '';
  private _saving = false;
  private _form: FormState = emptyForm();

  protected render(): string {
    const user = currentUser.value;
    if (!user) return '<style>:host{display:block}</style>';

    const style = `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 420px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .notice { font-size: var(--font-size-sm); color: var(--color-text-secondary);
          background: var(--color-bg-secondary); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); padding: var(--space-3); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input {
          padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base);
          background: var(--color-bg-primary); color: var(--color-text-primary);
        }
        input:focus { outline: none; border-color: var(--color-border-focus); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover:not(:disabled) { background: var(--color-accent-hover); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-left: var(--space-3); }
        .feedback { font-size: var(--font-size-sm); margin-top: var(--space-3); }
        .feedback.success { color: var(--color-success); }
        .feedback.error   { color: var(--color-danger); }
      </style>
    `;

    if (user.auth_provider !== 'password') {
      const message = user.auth_provider === 'guest'
        ? t('screen.change_password.provider_guest')
        : t('screen.change_password.provider_oauth');
      return `
        ${style}
        <pi-header-bar></pi-header-bar>
        <div class="page">
          <h2>${t('screen.change_password.title')}</h2>
          <div class="notice">${message}</div>
        </div>
      `;
    }

    const forced = user.must_change_password;

    return `
      ${style}
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <h2>${t('screen.change_password.title')}</h2>
        ${forced ? `<div class="notice">${t('screen.change_password.forced_notice')}</div>` : ''}

        ${!forced ? `
          <div class="field">
            <label for="current-password">${t('screen.change_password.current_password')}</label>
            <input type="password" id="current-password" autocomplete="current-password" value="${this._form.currentPassword}" />
          </div>
        ` : ''}

        <div class="field">
          <label for="new-password">${t('screen.change_password.new_password')}</label>
          <input type="password" id="new-password" autocomplete="new-password" value="${this._form.newPassword}" />
        </div>

        <div class="field">
          <label for="confirm-password">${t('screen.change_password.confirm_password')}</label>
          <input type="password" id="confirm-password" autocomplete="new-password" value="${this._form.confirmPassword}" />
        </div>

        ${this._error ? `<div class="feedback error">${this._error}</div>` : ''}

        <div>
          <button class="btn" id="submit-btn" ${this._saving ? 'disabled' : ''}>
            ${this._saving ? t('settings.saving') : t('common.button.save')}
          </button>
          ${!forced ? `<button class="btn-outline" id="back-btn">${t('common.button.back')}</button>` : ''}
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('submit-btn')?.addEventListener('click', () => void this._doSubmit());
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/app/settings'));

    // Keep _form in sync so values survive the full re-render a validation
    // error or the _saving flag triggers (BaseComponent replaces innerHTML,
    // which would otherwise blank every field on each attempt).
    (['current-password', 'new-password', 'confirm-password'] as const).forEach((id) => {
      this.shadow.getElementById(id)?.addEventListener('input', (e) => {
        const value = (e.target as HTMLInputElement).value;
        if (id === 'current-password') this._form.currentPassword = value;
        else if (id === 'new-password') this._form.newPassword = value;
        else this._form.confirmPassword = value;
      });
    });
  }

  private async _doSubmit(): Promise<void> {
    const user = currentUser.value;
    if (!user) return;

    const forced = user.must_change_password;
    const { currentPassword, newPassword, confirmPassword } = this._form;

    if (!forced && !currentPassword) {
      this._error = t('validation.required');
      this._rerender();
      return;
    }
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      this._error = t('validation.password.min_length', { min: MIN_PASSWORD_LENGTH });
      this._rerender();
      return;
    }
    if (newPassword !== confirmPassword) {
      this._error = t('validation.password.mismatch');
      this._rerender();
      return;
    }

    this._error = '';
    this._saving = true;
    this._rerender();
    try {
      const updated = await changePassword({
        current_password: forced ? undefined : currentPassword,
        new_password: newPassword,
      });
      updateCurrentUser(updated);
      const redirect = consumeRedirectAfterLogin();
      navigate(redirect ?? '/app/portfolios');
    } catch (ex) {
      this._error = (ex as Error).message;
      this._saving = false;
      this._rerender();
    }
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }
}

customElements.define('pi-change-password-screen', ChangePasswordScreen);
