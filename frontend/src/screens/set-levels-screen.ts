import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import '../components/price-level-form.js';
import { t } from '../i18n/i18n.js';
import { listPriceLevels, deletePriceLevel } from '../api/price-levels.js';
import { getHolding } from '../api/holdings.js';
import { getAssetPrice } from '../api/market-data.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { PriceLevel } from '../api/types.js';
import { formatCurrency } from '../utils/format.js';

export class SetLevelsScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _levels: PriceLevel[] = [];
  private _currentPrice: number | null = null;
  private _quoteCurrency = 'EUR';

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    const [levelsResult, holdingResult] = await Promise.allSettled([
      listPriceLevels(this._portfolioId, this._holdingId),
      getHolding(this._portfolioId, this._holdingId),
    ]);

    this._levels = levelsResult.status === 'fulfilled' ? levelsResult.value : [];
    const holding = holdingResult.status === 'fulfilled' ? holdingResult.value : null;
    if (holding) this._quoteCurrency = holding.asset.quote_currency;

    // Render immediately with the levels we already have — don't block on the
    // (potentially slow, live-provider-backed) current-price lookup below.
    this.shadow.innerHTML = this.render();
    this._wire();

    if (holding) {
      try {
        const price = await getAssetPrice(holding.asset.ticker, holding.asset.market);
        this._currentPrice = Number(price.price);
      } catch {
        this._currentPrice = null;
      }
      const form = this.shadow.getElementById('form') as (HTMLElement & { currentPrice: number | null }) | null;
      if (form) form.currentPrice = this._currentPrice;
    }
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 560px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-4); }
        h3 { font-size: var(--font-size-base); color: var(--color-text-secondary); margin: var(--space-6) 0 var(--space-3); }
        .level { display: flex; align-items: center; justify-content: space-between;
          padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          margin-bottom: var(--space-2); }
        .level-status { font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-left: var(--space-2); }
        .del-btn { padding: 1px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); border: 1px solid var(--color-danger); color: var(--color-danger); }
        .del-btn:hover { background: var(--color-danger); color: #fff; }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="page">
        <h2>${t('set_levels.title')}</h2>
        <pi-price-level-form id="form"></pi-price-level-form>
        <h3>${t('set_levels.existing')}</h3>
        <div id="levels-list">
          ${this._levels.map((l) => `
            <div class="level">
              <span>
                ${formatCurrency(l.target_price, this._quoteCurrency)} ${t('screen.price_level.direction.' + l.direction)}
                ${l.note ? `— ${l.note}` : ''}
                <span class="level-status">${t('screen.price_level.status.' + l.status)}</span>
              </span>
              <button class="del-btn" data-id="${l.id}">${t('common.button.delete')}</button>
            </div>
          `).join('')}
        </div>
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    this._wire();
  }

  private _wire(): void {
    const form = this.shadow.getElementById('form') as HTMLElement & {
      portfolioId: string;
      holdingId: string;
      currentPrice: number | null;
    };
    if (form) {
      form.portfolioId = this._portfolioId;
      form.holdingId = this._holdingId;
      form.currentPrice = this._currentPrice;
    }
    this.shadow.getElementById('form')?.addEventListener('level-created', () => void this._load());
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/app/portfolios/${this._portfolioId}/assets/${this._holdingId}`));
    this.shadow.querySelectorAll('.del-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const levelId = (btn as HTMLElement).dataset['id']!;
        await deletePriceLevel(this._portfolioId, this._holdingId, levelId, this._currentPrice ?? undefined);
        void this._load();
      });
    });
  }
}

customElements.define('pi-set-levels-screen', SetLevelsScreen);
