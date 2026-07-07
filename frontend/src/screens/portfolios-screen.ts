import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listPortfolios, updatePortfolio, archivePortfolio, restorePortfolio, deletePortfolio } from '../api/portfolios.js';
import { navigate } from '../router/router.js';
import type { Portfolio } from '../api/types.js';

export class PortfoliosScreen extends BaseComponent {
  private _portfolios: Portfolio[] = [];
  private _loading = true;
  private _showArchived = false;
  private _renameId: string | null = null;
  private _renameValue = '';
  private _confirmArchiveId: string | null = null;
  private _confirmDeleteId: string | null = null;
  private _error = '';

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this.shadow.innerHTML = this.render();
    try {
      this._portfolios = await listPortfolios(this._showArchived);
    } catch (ex) {
      this._error = (ex as Error).message;
    }
    this._loading = false;
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 640px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); flex-wrap: wrap; gap: var(--space-2); }
        h2 { font-size: var(--font-size-xl); }
        .header-actions { display: flex; gap: var(--space-2); align-items: center; }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover { background: var(--color-accent-hover); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover { background: var(--color-bg-surface); }
        .btn-sm { background: var(--color-accent); color: #fff; padding: 2px var(--space-3);
          border-radius: var(--radius-sm); font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); }
        .btn-sm:hover { background: var(--color-accent-hover); }
        .btn-ghost { padding: 2px var(--space-3); border-radius: var(--radius-sm);
          font-size: var(--font-size-sm); color: var(--color-text-secondary);
          border: 1px solid var(--color-border); }
        .btn-ghost:hover { background: var(--color-bg-surface); }
        .btn-danger { padding: 2px var(--space-3); border-radius: var(--radius-sm);
          font-size: var(--font-size-sm); color: var(--color-danger);
          border: 1px solid var(--color-danger); }
        .btn-danger:hover { background: var(--color-danger); color: #fff; }
        .btn-link { color: var(--color-text-secondary); font-size: var(--font-size-sm);
          text-decoration: underline; padding: 2px var(--space-2); }
        .card {
          border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); margin-bottom: var(--space-3);
          transition: box-shadow 0.15s;
        }
        .card.active { cursor: pointer; }
        .card.active:hover { box-shadow: var(--elevation-2); }
        .card.archived { opacity: 0.75; background: var(--color-bg-secondary); }
        .card-top { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
        .name { font-weight: var(--font-weight-semibold); flex: 1; min-width: 0; }
        .meta { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: 4px; }
        .card-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; margin-top: var(--space-2); }
        .confirm-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); }
        .confirm-label { color: var(--color-text-secondary); }
        .rename-input { border: 1px solid var(--color-accent); border-radius: var(--radius-sm);
          padding: 2px var(--space-2); font-size: var(--font-size-sm); flex: 1; min-width: 0;
          background: var(--color-bg-primary); color: var(--color-text-primary); }
        .error-msg { color: var(--color-danger); font-size: var(--font-size-sm); margin-top: var(--space-2); }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .section-label { font-size: var(--font-size-xs); color: var(--color-text-muted);
          text-transform: uppercase; letter-spacing: 0.05em; margin: var(--space-4) 0 var(--space-2); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <div class="header">
          <h2>${t('screen.portfolios.title')}</h2>
          <div class="header-actions">
            <button class="btn-outline" id="toggle-archived-btn">
              ${this._showArchived ? t('screen.portfolios.hide_archived') : t('screen.portfolios.archived')}
            </button>
            <button class="btn" id="new-btn">${t('screen.portfolios.create')}</button>
          </div>
        </div>
        ${this._error ? `<div class="error-msg">${this._error}</div>` : ''}
        ${this._loading
          ? `<div class="empty">${t('common.loading')}</div>`
          : this._renderList()}
      </div>
    `;
  }

  private _renderList(): string {
    const active = this._portfolios.filter((p) => p.status === 'active');
    const archived = this._portfolios.filter((p) => p.status === 'archived');
    if (active.length === 0 && archived.length === 0) {
      return `<div class="empty">${t('screen.portfolios.empty')}</div>`;
    }
    return `
      <div class="list">
        ${active.map((p) => this._renderActiveCard(p)).join('')}
        ${this._showArchived && archived.length > 0
          ? `<div class="section-label">${t('screen.portfolios.archived')}</div>
             ${archived.map((p) => this._renderArchivedCard(p)).join('')}`
          : ''}
      </div>
    `;
  }

  private _renderActiveCard(p: Portfolio): string {
    const isRenaming = this._renameId === p.id;
    const isConfirmingArchive = this._confirmArchiveId === p.id;
    return `
      <div class="card active" data-id="${p.id}">
        <div class="card-top">
          ${isRenaming
            ? `<input class="rename-input" id="rename-input-${p.id}" value="${this._renameValue}" />`
            : `<div class="name">${p.name}</div>`}
          <div style="display:flex;gap:var(--space-2)">
            ${isRenaming
              ? `<button class="btn-sm" data-save-rename="${p.id}">${t('common.button.save')}</button>
                 <button class="btn-ghost" data-cancel-rename="${p.id}">${t('common.button.cancel')}</button>`
              : isConfirmingArchive
                ? `<span class="confirm-label">${t('screen.portfolio.archive.confirm')}</span>
                   <button class="btn-danger" data-do-archive="${p.id}">${t('common.button.confirm')}</button>
                   <button class="btn-ghost" data-cancel-archive="${p.id}">${t('common.button.cancel')}</button>`
                : `<button class="btn-ghost" data-rename="${p.id}">${t('screen.portfolio.rename')}</button>
                   <button class="btn-ghost" data-archive="${p.id}">${t('screen.portfolio.archive')}</button>`}
          </div>
        </div>
        <div class="meta">${p.base_currency} · ${p.status}</div>
      </div>
    `;
  }

  private _renderArchivedCard(p: Portfolio): string {
    const isConfirmingDelete = this._confirmDeleteId === p.id;
    return `
      <div class="card archived" data-id="${p.id}">
        <div class="card-top">
          <div class="name">${p.name}</div>
        </div>
        <div class="meta">${p.base_currency} · ${p.status}</div>
        <div class="card-actions">
          <button class="btn-ghost" data-restore="${p.id}">${t('screen.portfolio.restore')}</button>
          ${isConfirmingDelete
            ? `<span class="confirm-label">${t('screen.portfolio.delete.confirm')}</span>
               <button class="btn-danger" data-do-delete="${p.id}">${t('common.button.confirm')}</button>
               <button class="btn-ghost" data-cancel-delete="${p.id}">${t('common.button.cancel')}</button>`
            : `<button class="btn-danger" data-delete="${p.id}">${t('screen.portfolio.delete')}</button>`}
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('new-btn')?.addEventListener('click', () => navigate('/portfolios/new'));
    this.shadow.getElementById('toggle-archived-btn')?.addEventListener('click', () => {
      this._showArchived = !this._showArchived;
      void this._load();
    });

    // Active card navigation (only card-top clicks on non-interactive area)
    this.shadow.querySelectorAll<HTMLElement>('.card.active').forEach((card) => {
      card.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        if (target.closest('button') || target.closest('input')) return;
        navigate(`/portfolios/${card.dataset['id']}`);
      });
    });

    // Rename flow
    this.shadow.querySelectorAll<HTMLElement>('[data-rename]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.dataset['rename']!;
        const p = this._portfolios.find((x) => x.id === id);
        this._renameId = id;
        this._renameValue = p?.name ?? '';
        this._confirmArchiveId = null;
        this._rerender();
        this.shadow.querySelector<HTMLInputElement>(`#rename-input-${id}`)?.focus();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-save-rename]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doRename(btn.dataset['saveRename']!));
    });
    this.shadow.querySelectorAll<HTMLInputElement>('[id^="rename-input-"]').forEach((inp) => {
      inp.addEventListener('input', () => { this._renameValue = inp.value; });
      inp.addEventListener('keydown', (e) => {
        const id = inp.id.replace('rename-input-', '');
        if (e.key === 'Enter') void this._doRename(id);
        if (e.key === 'Escape') { this._renameId = null; this._rerender(); }
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-cancel-rename]').forEach((btn) => {
      btn.addEventListener('click', () => { this._renameId = null; this._rerender(); });
    });

    // Archive flow
    this.shadow.querySelectorAll<HTMLElement>('[data-archive]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmArchiveId = btn.dataset['archive']!;
        this._renameId = null;
        this._rerender();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-do-archive]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doArchive(btn.dataset['doArchive']!));
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-cancel-archive]').forEach((btn) => {
      btn.addEventListener('click', () => { this._confirmArchiveId = null; this._rerender(); });
    });

    // Restore / Delete flow (archived)
    this.shadow.querySelectorAll<HTMLElement>('[data-restore]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doRestore(btn.dataset['restore']!));
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-delete]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmDeleteId = btn.dataset['delete']!;
        this._rerender();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-do-delete]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doDelete(btn.dataset['doDelete']!));
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-cancel-delete]').forEach((btn) => {
      btn.addEventListener('click', () => { this._confirmDeleteId = null; this._rerender(); });
    });
  }

  private async _doRename(id: string): Promise<void> {
    const name = this._renameValue.trim();
    if (!name) return;
    try {
      await updatePortfolio(id, { name });
      this._renameId = null;
      await this._load();
    } catch (ex) {
      this._error = (ex as Error).message;
      this._rerender();
    }
  }

  private async _doArchive(id: string): Promise<void> {
    try {
      await archivePortfolio(id);
      this._confirmArchiveId = null;
      await this._load();
    } catch (ex) {
      this._error = (ex as Error).message;
      this._confirmArchiveId = null;
      this._rerender();
    }
  }

  private async _doRestore(id: string): Promise<void> {
    try {
      await restorePortfolio(id);
      await this._load();
    } catch (ex) {
      this._error = (ex as Error).message;
      this._rerender();
    }
  }

  private async _doDelete(id: string): Promise<void> {
    try {
      await deletePortfolio(id);
      this._confirmDeleteId = null;
      await this._load();
    } catch (ex) {
      this._error = (ex as Error).message;
      this._confirmDeleteId = null;
      this._rerender();
    }
  }
}

customElements.define('pi-portfolios-screen', PortfoliosScreen);
