import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { login, guestLogin } from '../api/auth.js';
import { setAuthState, currentUser } from '../state/auth-state.js';
import { currentLanguage } from '../state/language-state.js';
import { navigate, consumeRedirectAfterLogin } from '../router/router.js';
import { listPortfolios } from '../api/portfolios.js';
import type { LoginResponse } from '../api/types.js';

export class LoginScreen extends BaseComponent {
  protected render(): string {
    if (currentUser.value) return '<style>:host{display:block}</style>';
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
        .lang { text-align: right; margin-bottom: var(--space-4); font-size: var(--font-size-sm); }
        .lang select { border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 2px; }
      </style>
      <div class="card">
        <div class="lang">
          <select id="lang-select">
            <option value="es" ${currentLanguage.value === 'es' ? 'selected' : ''}>ES</option>
            <option value="en" ${currentLanguage.value === 'en' ? 'selected' : ''}>EN</option>
          </select>
        </div>
        <h1>${t('login.title')}</h1>
        <div class="field">
          <label for="email">${t('login.email')}</label>
          <input type="email" id="email" autocomplete="email" />
        </div>
        <div class="field">
          <label for="password">${t('login.password')}</label>
          <input type="password" id="password" autocomplete="current-password" />
        </div>
        <div id="error" class="error"></div>
        <button class="btn-primary" id="login-btn">${t('login.submit')}</button>
        <button class="btn-secondary" id="guest-btn">${t('login.guest')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('lang-select')?.addEventListener('change', (e) => {
      currentLanguage.value = (e.target as HTMLSelectElement).value;
    });
    this.shadow.getElementById('login-btn')?.addEventListener('click', () => void this._doLogin());
    this.shadow.getElementById('guest-btn')?.addEventListener('click', () => void this._doGuest());
  }

  private async _doLogin(): Promise<void> {
    const email = (this.shadow.getElementById('email') as HTMLInputElement).value;
    const password = (this.shadow.getElementById('password') as HTMLInputElement).value;
    await this._handleResponse(() => login({ email, password }));
  }

  private async _doGuest(): Promise<void> {
    const email = (this.shadow.getElementById('email') as HTMLInputElement).value;
    await this._handleResponse(() => guestLogin({ email }));
  }

  private async _handleResponse(fn: () => Promise<LoginResponse>): Promise<void> {
    const errEl = this.shadow.getElementById('error')!;
    errEl.textContent = '';
    try {
      const res = await fn();
      setAuthState(res.user, res.session.notifications_poll_interval_seconds, res.session.csrf_token);
      const redirect = consumeRedirectAfterLogin();
      if (redirect) { navigate(redirect); return; }
      // Post-login routing (D02 §10)
      const count = res.session.portfolios_count;
      if (count === 0) { navigate('/portfolios/new'); return; }
      if (count === 1) {
        const portfolios = await listPortfolios();
        navigate(`/portfolios/${portfolios[0].id}`);
      } else {
        navigate('/portfolios');
      }
    } catch (ex) {
      errEl.textContent = (ex as Error).message;
    }
  }
}

customElements.define('pi-login-screen', LoginScreen);
