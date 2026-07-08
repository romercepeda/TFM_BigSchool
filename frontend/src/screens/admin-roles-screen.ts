import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listAdminRoles } from '../api/admin.js';
import type { AdminRoleOut } from '../api/types.js';
import { navigate } from '../router/router.js';

export class AdminRolesScreen extends BaseComponent {
  private _roles: AdminRoleOut[] = [];
  private _loading = true;
  private _error = '';

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._rerender();
    try {
      this._roles = await listAdminRoles();
    } catch (ex) {
      this._error = (ex as Error).message;
    }
    this._loading = false;
    this._rerender();
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 720px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2); }
        h2 { font-size: var(--font-size-xl); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover { background: var(--color-bg-surface); }
        .tabs { display: flex; gap: var(--space-2); margin: var(--space-4) 0; }
        .tab { padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm); font-size: var(--font-size-sm); color: var(--color-text-secondary); border: 1px solid var(--color-border); }
        .tab.active { background: var(--color-accent); color: #fff; border-color: var(--color-accent); }
        .card { border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); margin-bottom: var(--space-4); }
        .card-title { display: flex; align-items: center; gap: var(--space-2); font-weight: var(--font-weight-semibold);
          font-size: var(--font-size-lg); margin-bottom: var(--space-1); }
        .badge-sm { font-size: var(--font-size-xs); padding: 2px var(--space-2); border-radius: var(--radius-sm);
          background: var(--color-bg-secondary); border: 1px solid var(--color-border); color: var(--color-text-secondary); }
        .description { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-3); }
        .perm-list { display: flex; flex-wrap: wrap; gap: var(--space-1); }
        .perm-badge { font-family: monospace; font-size: var(--font-size-xs); padding: 2px 6px;
          background: var(--color-bg-secondary); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); font-size: var(--font-size-sm); margin-bottom: var(--space-3); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <div class="header">
          <h2>${t('admin.roles.title')}</h2>
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
        </div>
        <div class="tabs">
          <span class="tab" id="users-tab">${t('admin.users.title')}</span>
          <span class="tab active">${t('admin.roles.title')}</span>
        </div>
        ${this._error ? `<div class="error-msg">${this._error}</div>` : ''}
        ${this._loading
          ? `<div class="empty">${t('common.loading')}</div>`
          : this._roles.map((r) => `
              <div class="card">
                <div class="card-title">
                  ${r.name}
                  ${r.is_default ? `<span class="badge-sm">${t('admin.roles.default')}</span>` : ''}
                  ${r.is_admin_role ? `<span class="badge-sm">${t('admin.roles.admin_role')}</span>` : ''}
                </div>
                <div class="description">${r.description}</div>
                <div class="perm-list">
                  ${r.permissions.map((p) => `<span class="perm-badge">${p}</span>`).join('')}
                </div>
              </div>
            `).join('')}
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('users-tab')?.addEventListener('click', () => navigate('/app/admin/users'));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/app/portfolios'));
  }
}

customElements.define('pi-admin-roles-screen', AdminRolesScreen);
