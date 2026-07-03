// Data providers editor — Spec D12 §7, Changeset C04 §5.
// Drag-and-drop reorder uses the native HTML5 Drag and Drop API (no new
// dependency, per Changeset C04 §5 / §12).

import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { getDataProviders, updateDataProviders, resetDataProviders } from '../api/settings.js';
import type { DataProvidersResponse } from '../api/types.js';
import { hasPermission } from '../state/auth-state.js';
import { navigate } from '../router/router.js';

type ListKind = 'market' | 'fx';

const DISPLAY_NAMES: Record<string, string> = {
  twelve_data: 'Twelve Data',
  eodhd: 'EODHD',
  finnhub: 'Finnhub',
  frankfurter: 'Frankfurter',
};

export class DataProvidersEditor extends BaseComponent {
  private _data: DataProvidersResponse | null = null;
  private _marketProviders: string[] = [];
  private _fxProviders: string[] = [];
  private _loading = true;
  private _saving = false;
  private _saved = false;
  private _error = '';
  private _confirmEmptyList: ListKind | null = null;
  private _dragFrom: { list: ListKind; index: number } | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._rerender();
    try {
      this._data = await getDataProviders();
      this._marketProviders = [...this._data.market_data_providers];
      this._fxProviders = [...this._data.fx_data_providers];
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

  private _list(kind: ListKind): string[] {
    return kind === 'market' ? this._marketProviders : this._fxProviders;
  }

  private _setList(kind: ListKind, value: string[]): void {
    if (kind === 'market') this._marketProviders = value; else this._fxProviders = value;
  }

  private _available(kind: ListKind): string[] {
    const all = kind === 'market'
      ? (this._data?.market_data_available ?? [])
      : (this._data?.fx_data_available ?? []);
    const current = this._list(kind);
    return all.filter((p) => !current.includes(p));
  }

  private _renderKeyHint(provider: string): string {
    const status = this._data?.api_keys.find((k) => k.provider === provider);
    if (!status || !status.requires_api_key) return '';
    return status.configured
      ? `<span class="key-status ok">🔑 ${status.masked_key}</span>`
      : `<span class="key-status missing">${t('settings.data_providers.key_not_configured')}</span>`;
  }

  private _renderList(kind: ListKind, title: string): string {
    const items = this._list(kind);
    const available = this._available(kind);
    return `
      <div class="provider-list-block">
        <div class="list-title">${title}</div>
        <ul class="provider-list" data-list="${kind}">
          ${items.map((p, i) => `
            <li class="provider-item" draggable="true" data-list="${kind}" data-index="${i}">
              <span class="drag-handle">⠿</span>
              <span class="provider-name">${DISPLAY_NAMES[p] ?? p}</span>
              ${this._renderKeyHint(p)}
              <button class="remove-btn" data-list="${kind}" data-index="${i}" title="${t('common.button.delete')}">✕</button>
            </li>
          `).join('')}
        </ul>
        ${items.length === 0 ? `<div class="empty-hint">${t('settings.data_providers.empty_list')}</div>` : ''}
        ${this._confirmEmptyList === kind ? `
          <div class="confirm-row">
            <span>${t('settings.data_providers.confirm_empty')}</span>
            <button class="btn-xs-danger" data-confirm-empty="${kind}">${t('common.button.confirm')}</button>
            <button class="btn-xs" data-cancel-empty="${kind}">${t('common.button.cancel')}</button>
          </div>
        ` : ''}
        ${available.length > 0 ? `
          <div class="add-row">
            <select class="add-select" data-list="${kind}">
              ${available.map((p) => `<option value="${p}">${DISPLAY_NAMES[p] ?? p}</option>`).join('')}
            </select>
            <button class="btn-xs" data-add="${kind}">${t('common.button.add')}</button>
          </div>
        ` : ''}
      </div>
    `;
  }

  protected render(): string {
    if (this._loading) {
      return `<div class="loading">${t('common.loading')}</div>`;
    }
    if (this._error && !this._data) {
      return `<div class="feedback error">✗ ${this._error}</div>`;
    }

    return `
      <style>
        :host { display: block; }
        .loading { color: var(--color-text-muted); font-size: var(--font-size-sm); }
        .hint { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-4); }
        .provider-list-block { margin-bottom: var(--space-5); }
        .list-title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary); margin-bottom: var(--space-2); }
        .provider-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
        .provider-item { display: flex; align-items: center; gap: var(--space-2);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3); background: var(--color-bg-surface);
          cursor: grab; }
        .provider-item.drag-over { border-color: var(--color-accent); background: var(--color-accent-light); }
        .drag-handle { color: var(--color-text-muted); }
        .provider-name { flex: 1; font-size: var(--font-size-sm); }
        .key-status { font-size: var(--font-size-xs); }
        .key-status.ok { color: var(--color-text-secondary); }
        .key-status.missing { color: var(--color-danger); }
        .remove-btn { color: var(--color-text-muted); padding: 0 var(--space-2); }
        .remove-btn:hover { color: var(--color-danger); }
        .empty-hint { font-size: var(--font-size-sm); color: var(--color-danger); margin-top: var(--space-2); }
        .confirm-row { display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-2);
          font-size: var(--font-size-xs); color: var(--color-danger); flex-wrap: wrap; }
        .add-row { display: flex; gap: var(--space-2); margin-top: var(--space-3); align-items: center; }
        .add-select { padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); background: var(--color-bg-primary); color: var(--color-text-primary); }
        .btn-xs { border: 1px solid var(--color-border); padding: var(--space-1) var(--space-3);
          border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--color-text-secondary); }
        .btn-xs-danger { border: 1px solid var(--color-danger); padding: var(--space-1) var(--space-3);
          border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--color-danger); }
        .actions { display: flex; gap: var(--space-3); align-items: center; margin-top: var(--space-4); flex-wrap: wrap; }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .feedback { font-size: var(--font-size-sm); margin-top: var(--space-3); }
        .feedback.success { color: var(--color-success); }
        .feedback.error { color: var(--color-danger); }
        .failure-report-link { margin-top: var(--space-4); font-size: var(--font-size-sm); }
        .failure-report-link a { color: var(--color-accent); }
      </style>

      <div class="hint">${t('settings.data_providers.key_help')}</div>

      ${this._renderList('market', t('settings.data_providers.market_title'))}
      ${this._renderList('fx', t('settings.data_providers.fx_title'))}

      <div class="actions">
        <button class="btn" id="save-btn" ${this._saving ? 'disabled' : ''}>
          ${this._saving ? t('settings.saving') : t('common.button.save')}
        </button>
        <button class="btn-outline" id="reset-btn" ${this._saving ? 'disabled' : ''}>
          ${t('settings.data_providers.reset')}
        </button>
      </div>
      ${this._saved ? `<div class="feedback success">✓ ${t('settings.saved')}</div>` : ''}
      ${this._error ? `<div class="feedback error">✗ ${this._error}</div>` : ''}

      ${hasPermission('system.view_audit_log') ? `
        <div class="failure-report-link">
          <a href="#" id="failure-report-link">${t('settings.data_providers.view_failure_reports')}</a>
        </div>
      ` : ''}
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('failure-report-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      navigate('/admin/cascade-failures');
    });

    // Remove
    this.shadow.querySelectorAll<HTMLButtonElement>('.remove-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset['list'] as ListKind;
        const index = Number(btn.dataset['index']);
        const next = this._list(kind).filter((_, i) => i !== index);
        if (next.length === 0) {
          this._confirmEmptyList = kind;
          this._rerender();
          return;
        }
        this._setList(kind, next);
        this._saved = false;
        this._rerender();
      });
    });

    // Confirm/cancel removing the last provider from a list
    this.shadow.querySelectorAll<HTMLButtonElement>('[data-confirm-empty]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset['confirmEmpty'] as ListKind;
        this._setList(kind, []);
        this._confirmEmptyList = null;
        this._saved = false;
        this._rerender();
      });
    });
    this.shadow.querySelectorAll<HTMLButtonElement>('[data-cancel-empty]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmEmptyList = null;
        this._rerender();
      });
    });

    // Add
    this.shadow.querySelectorAll<HTMLButtonElement>('[data-add]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset['add'] as ListKind;
        const select = this.shadow.querySelector<HTMLSelectElement>(`.add-select[data-list="${kind}"]`);
        if (!select || !select.value) return;
        this._setList(kind, [...this._list(kind), select.value]);
        this._saved = false;
        this._rerender();
      });
    });

    // Drag and drop reorder (native HTML5 DnD — Changeset C04 §5)
    this.shadow.querySelectorAll<HTMLLIElement>('.provider-item').forEach((item) => {
      item.addEventListener('dragstart', () => {
        this._dragFrom = {
          list: item.dataset['list'] as ListKind,
          index: Number(item.dataset['index']),
        };
      });
      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (item.dataset['list'] === this._dragFrom?.list) {
          item.classList.add('drag-over');
        }
      });
      item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
      item.addEventListener('drop', (e) => {
        e.preventDefault();
        item.classList.remove('drag-over');
        const kind = item.dataset['list'] as ListKind;
        const toIndex = Number(item.dataset['index']);
        if (!this._dragFrom || this._dragFrom.list !== kind || this._dragFrom.index === toIndex) return;

        const list = [...this._list(kind)];
        const [moved] = list.splice(this._dragFrom.index, 1);
        list.splice(toIndex, 0, moved);
        this._setList(kind, list);
        this._dragFrom = null;
        this._saved = false;
        this._rerender();
      });
    });

    // Save
    this.shadow.getElementById('save-btn')?.addEventListener('click', () => void this._save());

    // Reset to defaults
    this.shadow.getElementById('reset-btn')?.addEventListener('click', () => void this._reset());
  }

  private async _save(): Promise<void> {
    this._saving = true;
    this._saved = false;
    this._error = '';
    this._rerender();
    try {
      this._data = await updateDataProviders(this._marketProviders, this._fxProviders);
      this._marketProviders = [...this._data.market_data_providers];
      this._fxProviders = [...this._data.fx_data_providers];
      this._saved = true;
    } catch (ex) {
      this._error = (ex as Error).message;
    } finally {
      this._saving = false;
      this._rerender();
    }
  }

  private async _reset(): Promise<void> {
    this._saving = true;
    this._saved = false;
    this._error = '';
    this._rerender();
    try {
      this._data = await resetDataProviders();
      this._marketProviders = [...this._data.market_data_providers];
      this._fxProviders = [...this._data.fx_data_providers];
      this._saved = true;
    } catch (ex) {
      this._error = (ex as Error).message;
    } finally {
      this._saving = false;
      this._rerender();
    }
  }
}

customElements.define('pi-data-providers-editor', DataProvidersEditor);
