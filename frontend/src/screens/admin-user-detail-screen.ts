import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { getAdminUserDetail, grantRole, revokeRole, resetUserPassword } from '../api/admin.js';
import type { AdminUserDetail } from '../api/types.js';
import { navigate } from '../router/router.js';
import { formatDateTime } from '../utils/format.js';
import type { RouteParams } from '../router/router.js';

// v1 role catalog is fixed to these two codes (D11 §5.2) — the roles screen
// is read-only, so there is no need to fetch the catalog just to render toggles.
const TOGGLEABLE_ROLES = ['investor', 'administrator'] as const;

export class AdminUserDetailScreen extends BaseComponent {
  private _userId = '';
  private _detail: AdminUserDetail | null = null;
  private _loading = true;
  private _error = '';
  private _roleError = '';
  private _resettingPassword = false;
  private _newPassword: string | null = null;
  private _resetError = '';

  set params(p: RouteParams) {
    this._userId = p['userId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._rerender();
    try {
      this._detail = await getAdminUserDetail(this._userId);
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
    const d = this._detail;
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 560px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); word-break: break-all; }
        .section { margin-bottom: var(--space-6); }
        .section-title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.05em;
          margin-bottom: var(--space-3); padding-bottom: var(--space-2); border-bottom: 1px solid var(--color-border); }
        .info-row { display: flex; align-items: center; gap: var(--space-3);
          font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-3); }
        .info-label { color: var(--color-text-muted); min-width: 140px; }
        .info-value { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
        .role-row { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
        .role-name { min-width: 140px; font-size: var(--font-size-sm); }
        .toggle { padding: var(--space-1) var(--space-3); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); border: 1px solid var(--color-border); }
        .toggle.on { background: var(--color-accent); color: #fff; border-color: var(--color-accent); }
        .toggle.off { color: var(--color-text-secondary); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover:not(:disabled) { background: var(--color-accent-hover); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover { background: var(--color-bg-surface); }
        .feedback { font-size: var(--font-size-sm); margin-top: var(--space-3); }
        .feedback.error { color: var(--color-danger); }
        .password-box { margin-top: var(--space-3); padding: var(--space-3);
          background: var(--color-bg-secondary); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); }
        .password-value { font-family: monospace; font-size: var(--font-size-base);
          font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
        .password-hint { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: var(--space-1); }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); padding: var(--space-4);
          border: 1px solid var(--color-danger); border-radius: var(--radius-sm); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        ${this._loading
          ? `<div class="empty">${t('common.loading')}</div>`
          : this._error
            ? `<div class="error-msg">${this._error}</div>`
            : d ? this._renderDetail(d) : ''}
        <div style="margin-top:var(--space-4)">
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
        </div>
      </div>
    `;
  }

  private _renderDetail(d: AdminUserDetail): string {
    return `
      <h2>${d.email}</h2>

      <div class="section">
        <div class="section-title">${t('admin.user_detail.info')}</div>
        <div class="info-row"><span class="info-label">${t('admin.users.provider')}</span><span class="info-value">${d.auth_provider}</span></div>
        <div class="info-row"><span class="info-label">${t('admin.users.created_at')}</span><span class="info-value">${formatDateTime(d.created_at)}</span></div>
        <div class="info-row"><span class="info-label">${t('admin.user_detail.portfolios_count')}</span><span class="info-value">${d.portfolios_count}</span></div>
        <div class="info-row"><span class="info-label">${t('admin.user_detail.must_change_password')}</span><span class="info-value">${d.must_change_password ? t('admin.user_detail.yes') : t('admin.user_detail.no')}</span></div>
      </div>

      <div class="section">
        <div class="section-title">${t('admin.user_detail.roles')}</div>
        ${TOGGLEABLE_ROLES.map((role) => {
          const held = d.roles.includes(role);
          return `
            <div class="role-row">
              <span class="role-name">${role}</span>
              <button class="toggle ${held ? 'on' : 'off'}" data-role="${role}">
                ${held ? t('admin.user_detail.role_held') : t('admin.user_detail.role_not_held')}
              </button>
            </div>
          `;
        }).join('')}
        ${this._roleError ? `<div class="feedback error">${this._roleError}</div>` : ''}
      </div>

      <div class="section">
        <div class="section-title">${t('admin.user_detail.password')}</div>
        ${d.auth_provider === 'password' ? `
          <button class="btn-outline" id="reset-password-btn" ${this._resettingPassword ? 'disabled' : ''}>
            ${this._resettingPassword ? t('settings.saving') : t('admin.user_detail.reset_password')}
          </button>
          ${this._newPassword ? `
            <div class="password-box">
              <div class="password-value">${this._newPassword}</div>
              <div class="password-hint">${t('admin.user_detail.new_password_hint')}</div>
            </div>
          ` : ''}
          ${this._resetError ? `<div class="feedback error">${this._resetError}</div>` : ''}
        ` : `<div class="password-hint">${t('admin.user_detail.no_password_provider')}</div>`}
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/admin/users'));

    this.shadow.querySelectorAll<HTMLElement>('[data-role]').forEach((btn) => {
      btn.addEventListener('click', () => void this._toggleRole(btn.dataset['role']!));
    });

    this.shadow.getElementById('reset-password-btn')?.addEventListener('click', () => void this._doResetPassword());
  }

  private async _toggleRole(role: string): Promise<void> {
    if (!this._detail) return;
    const held = this._detail.roles.includes(role);
    this._roleError = '';
    try {
      this._detail = held
        ? await revokeRole(this._userId, role)
        : await grantRole(this._userId, role);
    } catch (ex) {
      this._roleError = (ex as Error).message;
    }
    this._rerender();
  }

  private async _doResetPassword(): Promise<void> {
    this._resettingPassword = true;
    this._resetError = '';
    this._newPassword = null;
    this._rerender();
    try {
      const res = await resetUserPassword(this._userId);
      this._newPassword = res.new_password;
      this._detail = await getAdminUserDetail(this._userId);
    } catch (ex) {
      this._resetError = (ex as Error).message;
    } finally {
      this._resettingPassword = false;
      this._rerender();
    }
  }
}

customElements.define('pi-admin-user-detail-screen', AdminUserDetailScreen);
