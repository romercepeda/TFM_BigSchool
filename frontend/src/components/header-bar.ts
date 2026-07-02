import { BaseComponent } from './common/base-component.js';
import { currentUser, hasPermission } from '../state/auth-state.js';
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
    const tooltipText = count > 0
      ? t('nav.pending_jobs.tooltip').replace('{n}', String(count))
      : '';
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

        /* Badge wrapper — positions the tooltip relative to itself */
        .badge-wrap {
          position: relative;
          display: inline-flex; align-items: center;
          cursor: default;
        }
        .badge {
          background: var(--color-danger); color: #fff; border-radius: var(--radius-full);
          font-size: var(--font-size-xs); padding: 2px 7px;
          font-weight: var(--font-weight-semibold);
          animation: badge-pulse 1.8s ease-in-out infinite;
        }
        @keyframes badge-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.65; }
        }
        .badge-tooltip {
          display: none;
          position: absolute;
          top: calc(100% + 6px);
          right: 0;
          width: 260px;
          background: var(--color-bg-primary);
          border: 1px solid var(--color-border);
          border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3);
          font-size: var(--font-size-xs);
          color: var(--color-text-primary);
          line-height: 1.5;
          box-shadow: 0 4px 12px rgba(0,0,0,.15);
          z-index: 9999;
          white-space: normal;
          pointer-events: none;
        }
        .badge-tooltip::before {
          content: '';
          position: absolute;
          bottom: 100%; right: 10px;
          border: 5px solid transparent;
          border-bottom-color: var(--color-border);
        }
        .badge-tooltip::after {
          content: '';
          position: absolute;
          bottom: calc(100% - 1px); right: 11px;
          border: 4px solid transparent;
          border-bottom-color: var(--color-bg-primary);
        }
        .badge-wrap:hover .badge-tooltip { display: block; }
        .badge-label {
          font-weight: var(--font-weight-semibold);
          margin-bottom: var(--space-1);
          color: var(--color-danger);
        }

        button { color: var(--color-text-secondary); font-size: var(--font-size-sm); cursor: pointer; }
        button:hover { color: var(--color-accent); }
      </style>
      <header>
        <span class="brand">Portfolio IA</span>
        ${user ? `
          <div class="actions">
            ${count > 0 ? `
              <div class="badge-wrap" role="status" aria-label="${t('nav.pending_jobs')}">
                <span class="badge">${count}</span>
                <div class="badge-tooltip">
                  <div class="badge-label">⏳ ${t('nav.pending_jobs')}</div>
                  ${tooltipText}
                </div>
              </div>
            ` : ''}
            <span>${user.display_name ?? user.email}</span>
            ${hasPermission('user.list') || hasPermission('role.list')
              ? `<button id="admin-btn">${t('nav.admin')}</button>`
              : ''}
            <button id="settings-btn" title="${t('nav.configuration')}">⚙</button>
            <button id="logout-btn">${t('nav.logout')}</button>
          </div>
        ` : ''}
      </header>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('admin-btn')?.addEventListener('click', () => navigate('/admin/users'));
    this.shadow.getElementById('settings-btn')?.addEventListener('click', () => navigate('/settings'));
    this.shadow.getElementById('logout-btn')?.addEventListener('click', async () => {
      await logout();
      clearAuthState();
      stopPolling();
      navigate('/login');
    });
  }
}

customElements.define('pi-header-bar', HeaderBar);
