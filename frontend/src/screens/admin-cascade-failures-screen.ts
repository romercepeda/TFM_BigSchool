// Cascade failure report admin view — Spec D12 §7.4, Changeset C04 §6.
// Read-only, cross-user, filterable by date/provider/reason. No actions.

import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listCascadeFailureReports } from '../api/admin.js';
import type { CascadeFailureEntryOut } from '../api/types.js';
import { navigate } from '../router/router.js';
import { formatDateTime } from '../utils/format.js';

const PAGE_SIZE = 20;
const PROVIDERS = ['twelve_data', 'eodhd', 'finnhub'];
const REASONS = ['not_found', 'rate_limited', 'insufficient_lookback', 'provider_error'];

export class AdminCascadeFailuresScreen extends BaseComponent {
  private _items: CascadeFailureEntryOut[] = [];
  private _total = 0;
  private _page = 1;
  private _loading = true;
  private _error = '';
  private _fromDate = '';
  private _toDate = '';
  private _provider = '';
  private _reason = '';
  private _expandedId: string | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._rerender();
    try {
      const res = await listCascadeFailureReports({
        page: this._page,
        pageSize: PAGE_SIZE,
        fromDate: this._fromDate || undefined,
        toDate: this._toDate || undefined,
        provider: this._provider || undefined,
        reason: this._reason || undefined,
      });
      this._items = res.items;
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
    const totalPages = Math.max(1, Math.ceil(this._total / PAGE_SIZE));

    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 960px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        .filters { display: flex; gap: var(--space-3); flex-wrap: wrap; align-items: flex-end;
          margin-bottom: var(--space-4); padding: var(--space-4); border: 1px solid var(--color-border);
          border-radius: var(--radius-md); background: var(--color-bg-surface); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); }
        .field label { font-size: var(--font-size-xs); color: var(--color-text-secondary); }
        .field input, .field select { padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); background: var(--color-bg-primary); color: var(--color-text-primary); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover:not(:disabled) { background: var(--color-bg-surface); }
        .btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }
        .table { width: 100%; border-collapse: collapse; border: 1px solid var(--color-border);
          border-radius: var(--radius-md); overflow: hidden; }
        .table th { background: var(--color-bg-secondary); padding: var(--space-2) var(--space-3);
          font-size: var(--font-size-xs); text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--color-text-muted); text-align: left; border-bottom: 1px solid var(--color-border); }
        .table td { padding: var(--space-3); border-bottom: 1px solid var(--color-border); font-size: var(--font-size-sm); }
        .table tr:last-child td { border-bottom: none; }
        .table tr.row { cursor: pointer; }
        .table tr.row:hover { background: var(--color-bg-surface); }
        .reason-badge { display: inline-block; padding: 2px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); background: var(--color-bg-secondary); border: 1px solid var(--color-border); }
        .reason-badge.rate_limited { color: var(--color-danger); border-color: var(--color-danger); }
        .detail-row td { background: var(--color-bg-secondary); font-size: var(--font-size-xs);
          font-family: monospace; white-space: pre-wrap; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: var(--space-3); margin-top: var(--space-4); }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); font-size: var(--font-size-sm); margin-bottom: var(--space-3); }
        .back-row { margin-top: var(--space-4); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <h2>${t('admin.cascade_failures.title')}</h2>

        <div class="filters">
          <div class="field">
            <label>${t('admin.cascade_failures.from_date')}</label>
            <input type="date" id="from-date" value="${this._fromDate}" />
          </div>
          <div class="field">
            <label>${t('admin.cascade_failures.to_date')}</label>
            <input type="date" id="to-date" value="${this._toDate}" />
          </div>
          <div class="field">
            <label>${t('admin.cascade_failures.provider')}</label>
            <select id="provider-filter">
              <option value="">${t('admin.cascade_failures.all')}</option>
              ${PROVIDERS.map((p) => `<option value="${p}" ${this._provider === p ? 'selected' : ''}>${p}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>${t('admin.cascade_failures.reason')}</label>
            <select id="reason-filter">
              <option value="">${t('admin.cascade_failures.all')}</option>
              ${REASONS.map((r) => `<option value="${r}" ${this._reason === r ? 'selected' : ''}>${r}</option>`).join('')}
            </select>
          </div>
          <button class="btn-outline" id="apply-filters-btn">${t('admin.cascade_failures.apply')}</button>
        </div>

        ${this._error ? `<div class="error-msg">${this._error}</div>` : ''}
        ${this._loading
          ? `<div class="empty">${t('common.loading')}</div>`
          : this._items.length === 0
            ? `<div class="empty">${t('common.empty')}</div>`
            : `
              <table class="table">
                <thead><tr>
                  <th>${t('admin.cascade_failures.run_at')}</th>
                  <th>${t('admin.cascade_failures.ticker')}</th>
                  <th>${t('admin.cascade_failures.reason')}</th>
                  <th>${t('admin.cascade_failures.providers_tried')}</th>
                </tr></thead>
                <tbody>
                  ${this._items.map((item) => `
                    <tr class="row" data-id="${item.id}">
                      <td>${formatDateTime(item.run_completed_at)}</td>
                      <td>${item.ticker}</td>
                      <td><span class="reason-badge ${item.reason}">${item.reason}</span></td>
                      <td>${item.providers_tried.join(' → ')}</td>
                    </tr>
                    ${this._expandedId === item.id ? `
                      <tr class="detail-row"><td colspan="4">${JSON.stringify(item.last_error_by_provider, null, 2)}</td></tr>
                    ` : ''}
                  `).join('')}
                </tbody>
              </table>
              <div class="pagination">
                <button class="btn-outline" id="prev-btn" ${this._page <= 1 ? 'disabled' : ''}>${t('admin.users.prev')}</button>
                <span>${this._page} / ${totalPages}</span>
                <button class="btn-outline" id="next-btn" ${this._page >= totalPages ? 'disabled' : ''}>${t('admin.users.next')}</button>
              </div>
            `}

        <div class="back-row">
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/settings'));

    this.shadow.getElementById('apply-filters-btn')?.addEventListener('click', () => {
      this._fromDate = (this.shadow.getElementById('from-date') as HTMLInputElement).value;
      this._toDate = (this.shadow.getElementById('to-date') as HTMLInputElement).value;
      this._provider = (this.shadow.getElementById('provider-filter') as HTMLSelectElement).value;
      this._reason = (this.shadow.getElementById('reason-filter') as HTMLSelectElement).value;
      this._page = 1;
      void this._load();
    });

    this.shadow.querySelectorAll<HTMLElement>('.row').forEach((row) => {
      row.addEventListener('click', () => {
        const id = row.dataset['id'] ?? null;
        this._expandedId = this._expandedId === id ? null : id;
        this._rerender();
      });
    });

    this.shadow.getElementById('prev-btn')?.addEventListener('click', () => {
      this._page = Math.max(1, this._page - 1);
      void this._load();
    });
    this.shadow.getElementById('next-btn')?.addEventListener('click', () => {
      this._page += 1;
      void this._load();
    });
  }
}

customElements.define('pi-admin-cascade-failures-screen', AdminCascadeFailuresScreen);
