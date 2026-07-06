import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { addAsset } from '../api/holdings.js';
import { searchAssets } from '../api/market-data.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { AssetSearchResult } from '../api/types.js';
import { required, positiveNumber } from '../utils/validation.js';

export class AddAssetScreen extends BaseComponent {
  private _portfolioId = '';
  private _selectedAsset: AssetSearchResult | null = null;

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._selectedAsset = null;
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 480px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
        label { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        input[type="text"], input[type="number"], input[type="date"] {
          padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-base); width: 100%;
        }
        input:focus { outline: none; border-color: var(--color-border-focus); }

        /* Ticker typeahead */
        .ticker-wrap { position: relative; }
        .ticker-dropdown {
          display: none; position: absolute; top: 100%; left: 0; right: 0;
          background: var(--color-bg-primary); border: 1px solid var(--color-border);
          border-top: none; border-radius: 0 0 var(--radius-sm) var(--radius-sm);
          box-shadow: var(--elevation-2); max-height: 220px; overflow-y: auto;
          z-index: var(--z-dropdown);
        }
        .ticker-option {
          padding: var(--space-2) var(--space-3); cursor: pointer;
          font-size: var(--font-size-sm); border-bottom: 1px solid var(--color-border);
        }
        .ticker-option:last-child { border-bottom: none; }
        .ticker-option:hover { background: var(--color-bg-surface); }
        .ticker-option strong { color: var(--color-accent); }
        .ticker-hint { font-size: var(--font-size-xs); color: var(--color-success); margin-top: var(--space-1); min-height: 1em; }
        .ticker-searching { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: var(--space-1); }

        .actions { display: flex; gap: var(--space-3); margin-top: var(--space-4); }
        .btn-primary { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn-primary:hover { background: var(--color-accent-hover); }
        .btn-secondary { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-6);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); margin-top: var(--space-2); }
      </style>
      <div class="page">
        <h2>${t('add_asset.title')}</h2>

        <div class="field">
          <label>${t('add_asset.ticker')}</label>
          <div class="ticker-wrap">
            <input type="text" id="ticker-search"
              placeholder="${t('add_asset.ticker_placeholder')}"
              autocomplete="off" spellcheck="false" />
            <div id="ticker-dropdown" class="ticker-dropdown"></div>
          </div>
          <input type="hidden" id="ticker-value" />
          <div id="ticker-hint" class="ticker-hint"></div>
        </div>

        <div class="field">
          <label>${t('add_asset.quantity')}</label>
          <input type="number" id="quantity" step="0.0001" min="0" />
        </div>
        <div class="field">
          <label>${t('add_asset.cost')}</label>
          <input type="number" id="cost" step="0.01" min="0" />
        </div>
        <div class="field">
          <label>${t('add_asset.date')}</label>
          <input type="date" id="date" />
        </div>

        <div id="error" class="error"></div>
        <div class="actions">
          <button class="btn-primary" id="submit-btn">${t('common.button.add')}</button>
          <button class="btn-secondary" id="back-btn">${t('common.button.cancel')}</button>
        </div>
      </div>
    `;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}`));

    this._wireTypeahead();

    this.shadow.getElementById('submit-btn')?.addEventListener('click', async () => {
      const ticker = (this.shadow.getElementById('ticker-value') as HTMLInputElement).value.trim().toUpperCase();
      const qty    = (this.shadow.getElementById('quantity') as HTMLInputElement).value;
      const cost   = (this.shadow.getElementById('cost') as HTMLInputElement).value;
      const date   = (this.shadow.getElementById('date') as HTMLInputElement).value;
      const errEl  = this.shadow.getElementById('error')!;
      const err = required(ticker) ?? required(date) ?? positiveNumber(qty) ?? positiveNumber(cost);
      if (err) { errEl.textContent = t(err); return; }
      errEl.textContent = '';
      try {
        const asset = this._selectedAsset!;
        await addAsset(this._portfolioId, {
          asset: {
            ticker: asset.ticker,
            name: asset.name,
            asset_type: asset.asset_type,
            quote_currency: asset.quote_currency,
            market: asset.market,
          },
          lot: {
            purchase_date: date,
            quantity: Number(qty),
            unit_price: Number(cost),
            fx_rate_origin: 'auto',
          },
        });
        navigate(`/portfolios/${this._portfolioId}`);
      } catch (ex) {
        errEl.textContent = (ex as Error).message;
      }
    });
  }

  private _wireTypeahead(): void {
    const searchInput = this.shadow.getElementById('ticker-search') as HTMLInputElement;
    const dropdown    = this.shadow.getElementById('ticker-dropdown') as HTMLElement;
    const tickerVal   = this.shadow.getElementById('ticker-value') as HTMLInputElement;
    const hintEl      = this.shadow.getElementById('ticker-hint') as HTMLElement;
    let _debounce: ReturnType<typeof setTimeout> | null = null;

    const close = () => { dropdown.style.display = 'none'; };

    const pick = (r: AssetSearchResult) => {
      this._selectedAsset   = r;
      tickerVal.value       = r.ticker;
      searchInput.value     = r.ticker;
      hintEl.textContent    = r.name + (r.market ? ` · ${r.market}` : '');
      close();
    };

    const showResults = (results: AssetSearchResult[]) => {
      if (!results.length) { close(); return; }
      dropdown.innerHTML = results.map((r) =>
        `<div class="ticker-option" data-idx>
          <strong>${r.market ? r.market + ': ' : ''}${r.ticker}</strong> — ${r.name}
        </div>`
      ).join('');
      Array.from(dropdown.querySelectorAll('.ticker-option')).forEach((el, i) =>
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          pick(results[i]);
        })
      );
      dropdown.style.display = 'block';
    };

    searchInput.addEventListener('input', () => {
      this._selectedAsset   = null;
      tickerVal.value       = '';
      hintEl.textContent    = '';
      if (_debounce) clearTimeout(_debounce);
      const q = searchInput.value.trim();
      if (!q) { close(); return; }
      _debounce = setTimeout(async () => {
        try {
          showResults(await searchAssets(q));
        } catch {
          close();
        }
      }, 300);
    });

    searchInput.addEventListener('blur', close);
  }
}

customElements.define('pi-add-asset-screen', AddAssetScreen);
