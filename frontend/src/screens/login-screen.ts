import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { login, register, guestLogin } from '../api/auth.js';
import { setAuthState, currentUser } from '../state/auth-state.js';
import { navigate, consumeRedirectAfterLogin } from '../router/router.js';
import { ApiError } from '../api/types.js';
import { required, email as validateEmail, minLength, first } from '../utils/validation.js';
import type { LoginResponse } from '../api/types.js';

type Mode = 'login' | 'register';

export class LoginScreen extends BaseComponent {
  // C11 §2: the landing's "Crear cuenta" CTAs land on /app/register, a
  // distinct URL for the same screen — start in register mode there.
  // Temporarily forced to 'login' — registration and guest login are
  // disabled for now (existing accounts only, 2026-07-09). Revert this
  // line to re-enable the register mode toggle below.
  private _mode: Mode = 'login';
  private _fieldErrors: { email?: string; password?: string } = {};
  private _topError: string | null = null;
  private _emailExists = false;
  private _prefillEmail = '';

  protected render(): string {
    if (currentUser.value) return '<style>:host{display:block}</style>';
    const isRegister = this._mode === 'register';
    return `
      <style>
        :host { display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .card {
          width: 100%; max-width: 400px; padding: var(--space-8);
          border: 1px solid var(--color-border); border-radius: var(--radius-lg);
          box-shadow: var(--elevation-2);
        }
        h1 { font-size: var(--font-size-2xl); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input {
          padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base);
        }
        input:focus { outline: none; border-color: var(--color-border-focus); }
        .btn-primary {
          width: 100%; padding: var(--space-3); background: var(--color-accent);
          color: #fff; border-radius: var(--radius-sm); font-weight: var(--font-weight-medium);
          margin-top: var(--space-2);
        }
        .btn-primary:hover { background: var(--color-accent-hover); }
        .btn-secondary {
          width: 100%; padding: var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); margin-top: var(--space-3);
          color: var(--color-text-secondary);
        }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); margin-top: var(--space-2); }
        .field-error { color: var(--color-danger); font-size: var(--font-size-sm); }
        .mode-toggle { text-align: center; margin-top: var(--space-4); font-size: var(--font-size-sm); }
        .top-row {
          display: flex; justify-content: space-between; align-items: center;
          margin-bottom: var(--space-4); font-size: var(--font-size-sm);
        }
        .home-link {
          display: inline-flex; align-items: center; gap: var(--space-1);
          color: var(--color-text-secondary); text-decoration: none;
        }
        .home-link:hover { color: var(--color-text-primary); }
      </style>
      <div class="card">
        <div class="top-row">
          <a href="/" id="home-link" class="home-link" aria-label="${t('login.back_to_home')}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
            ${t('login.back_to_home')}
          </a>
        </div>
        <h1>${isRegister ? t('register.title') : t('login.title')}</h1>
        <div class="field">
          <label for="email">${t('login.email')}</label>
          <input type="email" id="email" autocomplete="email" value="${this._prefillEmail}" />
          ${this._fieldErrors.email ? `<div class="field-error">${t(this._fieldErrors.email)}</div>` : ''}
        </div>
        <div class="field">
          <label for="password">${t('login.password')}</label>
          <input type="password" id="password" autocomplete="${isRegister ? 'new-password' : 'current-password'}" />
          ${this._fieldErrors.password ? `<div class="field-error">${t(this._fieldErrors.password, { min: 8 })}</div>` : ''}
        </div>
        ${isRegister ? `
        <div class="field">
          <label for="display-name">${t('register.display_name.label')}</label>
          <input type="text" id="display-name" placeholder="${t('register.display_name.placeholder')}" />
        </div>` : ''}
        <div id="error" class="error">${this._renderTopError()}</div>
        <button class="btn-primary" id="submit-btn">${isRegister ? t('register.submit') : t('login.submit')}</button>
        <!-- Guest login and account creation temporarily disabled (existing
             accounts only, 2026-07-09) — restore these two blocks to re-enable:
        <button class="btn-secondary" id="guest-btn">${t('login.guest')}</button>
        <div class="mode-toggle">
          <a href="#" id="mode-toggle-link">${isRegister ? t('login.mode.toggle.to_login') : t('login.mode.toggle.to_register')}</a>
        </div>
        -->
      </div>
    `;
  }

  private _renderTopError(): string {
    if (this._emailExists) {
      return `${t('register.error.email_exists')} <a href="#" id="switch-to-login-link">${t('register.error.email_exists.action')}</a>`;
    }
    return this._topError ?? '';
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected afterRender(): void {
    this.shadow.getElementById('home-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      navigate('/');
    });
    this.shadow.getElementById('submit-btn')?.addEventListener('click', () => void this._doSubmit());
    this.shadow.getElementById('guest-btn')?.addEventListener('click', () => void this._doGuest());
    this.shadow.getElementById('mode-toggle-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      this._switchMode(this._mode === 'login' ? 'register' : 'login', '');
    });
    this.shadow.getElementById('switch-to-login-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      const email = (this.shadow.getElementById('email') as HTMLInputElement).value;
      this._switchMode('login', email);
    });
  }

  private _switchMode(mode: Mode, prefillEmail: string): void {
    this._mode = mode;
    this._fieldErrors = {};
    this._topError = null;
    this._emailExists = false;
    this._prefillEmail = prefillEmail;
    this._rerender();
  }

  private async _doSubmit(): Promise<void> {
    const email = (this.shadow.getElementById('email') as HTMLInputElement).value;
    const password = (this.shadow.getElementById('password') as HTMLInputElement).value;
    this._prefillEmail = email;

    const emailErr = first(() => required(email), () => validateEmail(email));
    const passwordErr = first(() => required(password), () => minLength(password, 8));
    if (emailErr || passwordErr) {
      this._fieldErrors = { email: emailErr ?? undefined, password: passwordErr ?? undefined };
      this._topError = null;
      this._emailExists = false;
      this._rerender();
      return;
    }
    this._fieldErrors = {};

    if (this._mode === 'register') {
      const displayNameInput = this.shadow.getElementById('display-name') as HTMLInputElement | null;
      const displayName = displayNameInput?.value.trim() || undefined;
      await this._handleResponse(() => register(email, password, displayName));
    } else {
      await this._handleResponse(() => login({ email, password }));
    }
  }

  private async _doGuest(): Promise<void> {
    const email = (this.shadow.getElementById('email') as HTMLInputElement).value;
    await this._handleResponse(() => guestLogin({ email }));
  }

  private async _handleResponse(fn: () => Promise<LoginResponse>): Promise<void> {
    this._topError = null;
    this._emailExists = false;
    try {
      const res = await fn();
      setAuthState(res.user, res.session.notifications_poll_interval_seconds, res.session.csrf_token);
      const redirect = consumeRedirectAfterLogin();
      // Post-login routing: always land on "My Portfolios" first, whether or
      // not the user has any yet — the list screen already handles the
      // empty-state with its own "create portfolio" CTA.
      navigate(redirect ?? '/app/portfolios');
    } catch (ex) {
      if (this._mode === 'register' && ex instanceof ApiError && ex.status === 409) {
        this._emailExists = true;
      } else {
        this._topError = (ex as Error).message;
      }
      this._rerender();
    }
  }
}

customElements.define('pi-login-screen', LoginScreen);
