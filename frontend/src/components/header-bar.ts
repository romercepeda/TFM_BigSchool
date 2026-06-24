import { BaseComponent } from './common/base-component.js';
import { currentUser } from '../state/auth-state.js';
import { pendingNotifications, startPolling, stopPolling } from '../state/notification-state.js';
import { pollIntervalSeconds } from '../state/auth-state.js';
import { getNotifications } from '../api/analyses.js';
import { logout } from '../api/auth.js';
import { clearAuthState } from '../state/auth-state.js';
import { navigate } from '../router/router.js';
import { t } from '../i18n/i18n.js';

export class HeaderBar extends BaseComponent {
  connectedCallback(): void {
    super.connectedCallback();
    if (currentUser.value) {
      startPolling(getNotifications, pollIntervalSeconds.value);
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    stopPolling();
  }

  protected render(): string {
    const user = currentUser.value;
    const count = pendingNotifications.value.length;
    return `
      <style>
        :host { display: block; }
        header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 0 var(--space-4); height: var(--header-height);
          background: var(--color-bg-primary); border-bottom: 1px solid var(--color-border);
          box-shadow: var(--shadow-sm);
        }
        .brand { font-weight: var(--font-weight-bold); color: var(--color-accent); font-size: var(--font-size-lg); }
        .actions { display: flex; align-items: center; gap: var(--space-3); }
        .badge { background: var(--color-danger); color: #fff; border-radius: var(--radius-full);
          font-size: var(--font-size-xs); padding: 2px 6px; }
        button { color: var(--color-text-secondary); font-size: var(--font-size-sm); cursor: pointer; }
        button:hover { color: var(--color-accent); }
      </style>
      <header>
        <span class="brand">Portfolio IA</span>
        ${user ? `
          <div class="actions">
            ${count > 0 ? `<span class="badge">${count}</span>` : ''}
            <span>${user.display_name ?? user.email}</span>
            <button id="logout-btn">${t('nav.logout')}</button>
          </div>
        ` : ''}
      </header>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('logout-btn')?.addEventListener('click', async () => {
      await logout();
      clearAuthState();
      stopPolling();
      navigate('/login');
    });
  }
}

customElements.define('pi-header-bar', HeaderBar);
