import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { listPortfolios } from '../api/portfolios.js';
import { navigate } from '../router/router.js';
import type { Portfolio } from '../api/types.js';

export class PortfoliosScreen extends BaseComponent {
  private _portfolios: Portfolio[] = [];
  private _loading = true;

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this.shadow.innerHTML = this.render();
    this._portfolios = await listPortfolios();
    this._loading = false;
    this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-4); }
        h2 { font-size: var(--font-size-xl); }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .list { padding: 0 var(--space-4); }
        .card {
          border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); margin-bottom: var(--space-3); cursor: pointer;
          transition: box-shadow 0.15s;
        }
        .card:hover { box-shadow: var(--shadow-md); }
        .name { font-weight: var(--font-weight-semibold); }
        .meta { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: 2px; }
        .empty { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
      </style>
      <div>
        <div class="header">
          <h2>${t('portfolios.title')}</h2>
          <button class="btn" id="new-btn">${t('portfolios.new')}</button>
        </div>
        <div class="list">
          ${this._loading
            ? `<div class="empty">${t('common.loading')}</div>`
            : this._portfolios.length === 0
              ? `<div class="empty">${t('portfolios.empty')}</div>`
              : this._portfolios.map((p) => `
                <div class="card" data-id="${p.id}">
                  <div class="name">${p.name}</div>
                  <div class="meta">${p.base_currency} · ${p.status}</div>
                </div>
              `).join('')}
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('new-btn')?.addEventListener('click', () => navigate('/portfolios/new'));
    this.shadow.querySelectorAll('.card').forEach((el) => {
      el.addEventListener('click', () => navigate(`/portfolios/${(el as HTMLElement).dataset['id']}`));
    });
  }
}

customElements.define('pi-portfolios-screen', PortfoliosScreen);
