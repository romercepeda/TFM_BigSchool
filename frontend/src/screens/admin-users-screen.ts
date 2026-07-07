import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listAdminUsers } from '../api/admin.js';
import type { AdminUserSummary } from '../api/types.js';
import { navigate } from '../router/router.js';
import { formatDate } from '../utils/format.js';

const PAGE_SIZE = 20;

export class AdminUsersScreen extends BaseComponent {
  private _users: AdminUserSummary[] = [];
  private _total = 0;
  private _offset = 0;
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
      const res = await listAdminUsers(PAGE_SIZE, this._offset);
      this._users = res.items;
      this._total = res.total;
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
    const page = Math.floor(this._offset / PAGE_SIZE) + 1;
    const totalPages = Math.max(1, Math.ceil(this._total / PAGE_SIZE));

    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 900px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); flex-wrap: wrap; gap: var(--space-2); }
        h2 { font-size: var(--font-size-xl); }
        .tabs { display: flex; gap: var(--space-2); margin-bottom: var(--space-4); }
        .tab { padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm); font-size: var(--font-size-sm); color: var(--color-text-secondary); border: 1px solid var(--color-border); }
        .tab.active { background: var(--color-accent); color: #fff; border-color: var(--color-accent); }
        .table { width: 100%; border-collapse: collapse; border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow: hidden; }
        .table th { background: var(--color-bg-secondary); padding: var(--space-2) var(--space-3);
          font-size: var(--font-size-xs); text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--color-text-muted); text-align: left; border-bottom: 1px solid var(--color-border); }
        .table td { padding: var(--space-3); border-bottom: 1px solid var(--color-border); font-size: var(--font-size-sm); }
        .table tr:last-child td { border-bottom: none; }
        .table tr.row { cursor: pointer; }
        .table tr.row:hover { background: var(--color-bg-surface); }
        .badge { display: inline-block; padding: 2px var(--space-2); background: var(--color-bg-secondary);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm); font-size: var(--font-size-xs);
          color: var(--color-text-secondary); margin-right: 4px; }
        .badge.admin { background: var(--color-accent); color: #fff; border-color: var(--color-accent); }
        .pagination { display: flex; justify-content: center; align-items: center; gap: var(--space-3); margin-top: var(--space-4); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover:not(:disabled) { background: var(--color-bg-surface); }
        .btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); font-size: var(--font-size-sm); margin-bottom: var(--space-3); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <div class="header">
          <h2>${t('admin.users.title')}</h2>
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
        </div>
        <div class="tabs">
          <span class="tab active">${t('admin.users.title')}</span>
          <span class="tab" id="roles-tab">${t('admin.roles.title')}</span>
        </div>
        ${this._error ? `<div class="error-msg">${this._error}</div>` : ''}
        ${this._loading
          ? `<div class="empty">${t('common.loading')}</div>`
          : this._users.length === 0
            ? `<div class="empty">${t('common.empty')}</div>`
            : `
              <table class="table">
                <thead><tr>
                  <th>${t('admin.users.email')}</th>
                  <th>${t('admin.users.provider')}</th>
                  <th>${t('admin.users.roles')}</th>
                  <th>${t('admin.users.created_at')}</th>
                </tr></thead>
                <tbody>
                  ${this._users.map((u) => `
                    <tr class="row" data-id="${u.id}">
                      <td>${u.email}</td>
                      <td>${u.auth_provider}</td>
                      <td>${u.roles.map((r) => `<span class="badge${r === 'administrator' ? ' admin' : ''}">${r}</span>`).join('') || '—'}</td>
                      <td>${formatDate(u.created_at)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
              <div class="pagination">
                <button class="btn-outline" id="prev-btn" ${this._offset === 0 ? 'disabled' : ''}>${t('admin.users.prev')}</button>
                <span>${page} / ${totalPages}</span>
                <button class="btn-outline" id="next-btn" ${this._offset + PAGE_SIZE >= this._total ? 'disabled' : ''}>${t('admin.users.next')}</button>
              </div>
            `}
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('roles-tab')?.addEventListener('click', () => navigate('/admin/roles'));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));

    this.shadow.querySelectorAll<HTMLElement>('.row').forEach((row) => {
      row.addEventListener('click', () => navigate(`/admin/users/${row.dataset['id']}`));
    });

    this.shadow.getElementById('prev-btn')?.addEventListener('click', () => {
      this._offset = Math.max(0, this._offset - PAGE_SIZE);
      void this._load();
    });
    this.shadow.getElementById('next-btn')?.addEventListener('click', () => {
      this._offset += PAGE_SIZE;
      void this._load();
    });
  }
}

customElements.define('pi-admin-users-screen', AdminUsersScreen);
