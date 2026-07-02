import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { navigate } from '../router/router.js';

// D11 §7.5 — shown in place of a screen the current user lacks permission for
// (typed URL, stale UI after a role change). Never reveals which permission
// was required, only that the operation is not authorized.
export class PermissionDeniedScreen extends BaseComponent {
  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-8); max-width: 480px; margin: 0 auto; text-align: center; }
        .icon { font-size: 48px; margin-bottom: var(--space-4); }
        p { color: var(--color-text-secondary); margin-bottom: var(--space-6); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover { background: var(--color-accent-hover); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <div class="icon">🔒</div>
        <p>${t('error.permission_denied')}</p>
        <button class="btn" id="dashboard-btn">${t('nav.portfolios')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('dashboard-btn')?.addEventListener('click', () => navigate('/portfolios'));
  }
}

customElements.define('pi-permission-denied-screen', PermissionDeniedScreen);
