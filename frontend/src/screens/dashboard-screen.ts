import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { getPortfolio, updatePortfolio, archivePortfolio } from '../api/portfolios.js';
import { listHoldings } from '../api/holdings.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { Holding, Portfolio } from '../api/types.js';

export class DashboardScreen extends BaseComponent {
  private _portfolioId = '';
  private _portfolio: Portfolio | null = null;
  private _holdings: Holding[] = [];
  private _loading = true;
  private _error = '';
  private _renaming = false;
  private _renameValue = '';
  private _confirmArchive = false;

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._renaming = false;
    this._confirmArchive = false;
    this.shadow.innerHTML = this.render();
    try {
      [this._portfolio, this._holdings] = await Promise.all([
        getPortfolio(this._portfolioId),
        listHoldings(this._portfolioId),
      ]);
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
        .content { padding: var(--space-6); max-width: var(--max-content-width); margin: 0 auto; }
        .portfolio-header { margin-bottom: var(--space-6); }
        .portfolio-name-row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
        .portfolio-name { font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
        .portfolio-meta { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: var(--space-1); }
        .actions { display: flex; gap: var(--space-3); margin-bottom: var(--space-6); flex-wrap: wrap; }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover { background: var(--color-accent-hover); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover { background: var(--color-bg-surface); }
        .btn-sm { padding: 2px var(--space-3); border-radius: var(--radius-sm);
          font-size: var(--font-size-sm); border: 1px solid var(--color-border);
          color: var(--color-text-secondary); }
        .btn-sm:hover { background: var(--color-bg-surface); }
        .btn-danger-sm { padding: 2px var(--space-3); border-radius: var(--radius-sm);
          font-size: var(--font-size-sm); border: 1px solid var(--color-danger); color: var(--color-danger); }
        .btn-danger-sm:hover { background: var(--color-danger); color: #fff; }
        .rename-input { border: 1px solid var(--color-accent); border-radius: var(--radius-sm);
          padding: 4px var(--space-3); font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold);
          background: var(--color-bg-primary); color: var(--color-text-primary); min-width: 200px; }
        .confirm-label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .section-title { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold);
          color: var(--color-text-primary); margin-bottom: var(--space-3); }
        .holdings-list { border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow: hidden; }
        .holding-row {
          display: flex; align-items: center; justify-content: space-between;
          padding: var(--space-4); border-bottom: 1px solid var(--color-border);
          cursor: pointer; transition: background 0.15s;
        }
        .holding-row:last-child { border-bottom: none; }
        .holding-row:hover { background: var(--color-bg-surface); }
        .holding-left { display: flex; flex-direction: column; gap: 2px; }
        .holding-ticker { font-weight: var(--font-weight-semibold); font-size: var(--font-size-base); }
        .holding-market { font-size: var(--font-size-xs); color: var(--color-text-muted); font-weight: normal; }
        .holding-name { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .holding-right { text-align: right; }
        .holding-price { font-weight: var(--font-weight-medium); }
        .holding-qty { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .loading { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); padding: var(--space-4); border: 1px solid var(--color-danger);
          border-radius: var(--radius-sm); margin-bottom: var(--space-4); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="content">
        ${this._loading
          ? `<div class="loading">${t('common.loading')}</div>`
          : this._error
            ? `<div class="error-msg">${this._error}</div>`
            : this._renderContent()}
      </div>
    `;
  }

  private _renderContent(): string {
    const p = this._portfolio;
    return `
      <div class="portfolio-header">
        <div class="portfolio-name-row">
          ${this._renaming
            ? `<input class="rename-input" id="rename-input" value="${this._renameValue}" />
               <button class="btn-sm" id="save-rename-btn">${t('common.button.save')}</button>
               <button class="btn-sm" id="cancel-rename-btn">${t('common.button.cancel')}</button>`
            : `<div class="portfolio-name">${p?.name ?? ''}</div>
               <button class="btn-sm" id="rename-btn">${t('screen.dashboard.rename')}</button>
               ${this._confirmArchive
                 ? `<span class="confirm-label">${t('screen.dashboard.archive.confirm')}</span>
                    <button class="btn-danger-sm" id="do-archive-btn">${t('common.button.confirm')}</button>
                    <button class="btn-sm" id="cancel-archive-btn">${t('common.button.cancel')}</button>`
                 : `<button class="btn-danger-sm" id="archive-btn">${t('screen.dashboard.archive')}</button>`}`}
        </div>
        <div class="portfolio-meta">${p?.base_currency ?? ''} · ${p?.status ?? ''}</div>
      </div>
      <div class="actions">
        <button class="btn" id="add-btn">${t('screen.dashboard.add_asset')}</button>
        <button class="btn-outline" id="alerts-btn">${t('screen.dashboard.alerts')}</button>
        <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
      </div>
      <div class="section-title">${t('screen.dashboard.holdings')}</div>
      ${this._holdings.length === 0
        ? `<div class="empty">${t('screen.dashboard.empty')}</div>`
        : `<div class="holdings-list">
            ${this._holdings.map((h) => `
              <div class="holding-row" data-id="${h.id}">
                <div class="holding-left">
                  <span class="holding-ticker">
                    ${h.asset.ticker}
                    ${h.asset.market ? `<span class="holding-market">${h.asset.market}</span>` : ''}
                  </span>
                  <span class="holding-name">${h.asset.name}</span>
                </div>
                <div class="holding-right">
                  <div class="holding-price">${Number(h.aggregates.avg_purchase_price_quote).toFixed(2)} ${h.asset.quote_currency}</div>
                  <div class="holding-qty">${Number(h.aggregates.quantity_held).toLocaleString()} ${t('screen.dashboard.units')}</div>
                </div>
              </div>
            `).join('')}
          </div>`}
    `;
  }

  protected afterRender(): void {
    const pid = this._portfolioId;

    this.shadow.getElementById('add-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}/add-asset`));
    this.shadow.getElementById('alerts-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${pid}/alerts`));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => navigate('/portfolios'));

    this.shadow.querySelectorAll('.holding-row').forEach((el) => {
      el.addEventListener('click', () =>
        navigate(`/portfolios/${pid}/assets/${(el as HTMLElement).dataset['id']}`));
    });

    // Rename
    this.shadow.getElementById('rename-btn')?.addEventListener('click', () => {
      this._renaming = true;
      this._renameValue = this._portfolio?.name ?? '';
      this._confirmArchive = false;
      this._rerender();
      this.shadow.querySelector<HTMLInputElement>('#rename-input')?.focus();
    });
    this.shadow.getElementById('save-rename-btn')?.addEventListener('click', () => void this._doRename());
    this.shadow.getElementById('cancel-rename-btn')?.addEventListener('click', () => {
      this._renaming = false;
      this._rerender();
    });
    const inp = this.shadow.querySelector<HTMLInputElement>('#rename-input');
    if (inp) {
      inp.addEventListener('input', () => { this._renameValue = inp.value; });
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') void this._doRename();
        if (e.key === 'Escape') { this._renaming = false; this._rerender(); }
      });
    }

    // Archive
    this.shadow.getElementById('archive-btn')?.addEventListener('click', () => {
      this._confirmArchive = true;
      this._renaming = false;
      this._rerender();
    });
    this.shadow.getElementById('do-archive-btn')?.addEventListener('click', () => void this._doArchive());
    this.shadow.getElementById('cancel-archive-btn')?.addEventListener('click', () => {
      this._confirmArchive = false;
      this._rerender();
    });
  }

  private async _doRename(): Promise<void> {
    const name = this._renameValue.trim();
    if (!name) return;
    try {
      this._portfolio = await updatePortfolio(this._portfolioId, { name });
      this._renaming = false;
      this._rerender();
    } catch (ex) {
      this._error = (ex as Error).message;
      this._renaming = false;
      this._rerender();
    }
  }

  private async _doArchive(): Promise<void> {
    try {
      await archivePortfolio(this._portfolioId);
      navigate('/portfolios');
    } catch (ex) {
      this._error = (ex as Error).message;
      this._confirmArchive = false;
      this._rerender();
    }
  }
}

customElements.define('pi-dashboard-screen', DashboardScreen);
