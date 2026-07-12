import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import '../components/indicator-card.js';
import { t } from '../i18n/i18n.js';
import { getHolding, deleteHolding, addLot, updateLot, deleteLot, updateAsset } from '../api/holdings.js';
import type { AddLotBody } from '../api/holdings.js';
import { listIndicators, getAssetIndicators } from '../api/indicators.js';
import { getAssetPrice } from '../api/market-data.js';
import { listPriceLevels, deletePriceLevel, markAlertSeen } from '../api/price-levels.js';
import { listDateAlerts, deleteDateAlert, markDateAlertSeen } from '../api/date-alerts.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { Holding, Indicator, IndicatorSnapshotHistory, PriceLevel, DateAlert } from '../api/types.js';
import { formatCurrency, formatDate, formatDateTime, formatNumber } from '../utils/format.js';

interface LotForm { date: string; qty: string; price: string; notes: string; }

const emptyLotForm = (): LotForm => ({ date: '', qty: '', price: '', notes: '' });

export class AssetDetailScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _holding: Holding | null = null;
  private _indicators: Indicator[] = [];
  private _indicatorHistories: IndicatorSnapshotHistory[] = [];
  private _priceLevels: PriceLevel[] = [];
  private _dateAlerts: DateAlert[] = [];
  private _currentPrice: number | null = null;
  private _priceFetchedAt = '';
  private _priceLoading = true;
  private _loading = true;
  private _error = '';

  // Delete holding
  private _confirmDeleteHolding = false;

  // Add lot form
  private _addingLot = false;
  private _addLotForm: LotForm = emptyLotForm();
  private _addLotError = '';

  // Edit lot
  private _editLotId: string | null = null;
  private _editLotForm: LotForm = emptyLotForm();
  private _editLotError = '';

  // Delete lot
  private _confirmDeleteLotId: string | null = null;
  private _deleteLotError = '';

  // Edit asset
  private _editingAsset = false;
  private _editAssetForm = { ticker: '', name: '', market: '' };
  private _editAssetError = '';

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this._error = '';
    this._confirmDeleteHolding = false;
    this._addingLot = false;
    this._editLotId = null;
    this._confirmDeleteLotId = null;
    this.shadow.innerHTML = this.render();

    try {
      this._holding = await getHolding(this._portfolioId, this._holdingId);
    } catch (ex) {
      this._error = (ex as Error).message;
      this._loading = false;
      this.shadow.innerHTML = this.render();
      return;
    }

    this._loading = false;
    this.shadow.innerHTML = this.render();
    this.afterRender();

    const ticker = this._holding.asset.ticker;
    const assetId = this._holding.asset.id;

    const [indResult, priceResult, levelsResult, dateAlertsResult] = await Promise.allSettled([
      Promise.all([listIndicators(), getAssetIndicators(assetId)]),
      getAssetPrice(ticker, this._holding.asset.market),
      listPriceLevels(this._portfolioId, this._holdingId),
      listDateAlerts(this._portfolioId, this._holdingId),
    ]);

    if (indResult.status === 'fulfilled') {
      const [allInds, histories] = indResult.value;
      this._indicators = allInds.filter((ind) => ind.scope === 'asset');
      this._indicatorHistories = histories;
    }
    if (priceResult.status === 'fulfilled') {
      this._currentPrice = Number(priceResult.value.price);
      this._priceFetchedAt = priceResult.value.fetched_at;
    }
    if (levelsResult.status === 'fulfilled') this._priceLevels = levelsResult.value;
    if (dateAlertsResult.status === 'fulfilled') this._dateAlerts = dateAlertsResult.value;
    this._priceLoading = false;

    this.shadow.innerHTML = this.render();
    this.afterRender();
    this._mountIndicatorCards();
  }

  private async _reloadAlerts(): Promise<void> {
    const [levelsResult, dateAlertsResult] = await Promise.allSettled([
      listPriceLevels(this._portfolioId, this._holdingId),
      listDateAlerts(this._portfolioId, this._holdingId),
    ]);
    if (levelsResult.status === 'fulfilled') this._priceLevels = levelsResult.value;
    if (dateAlertsResult.status === 'fulfilled') this._dateAlerts = dateAlertsResult.value;
    this._rerender();
  }

  private async _reloadHolding(): Promise<void> {
    try {
      this._holding = await getHolding(this._portfolioId, this._holdingId);
    } catch (ex) {
      this._error = (ex as Error).message;
    }
    this.shadow.innerHTML = this.render();
    this.afterRender();
    this._mountIndicatorCards();
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
    this._mountIndicatorCards();
  }

  protected render(): string {
    const h = this._holding;
    return `
      <style>
        :host { display: block; }
        .content { padding: var(--space-4); max-width: var(--max-content-width); margin: 0 auto; }
        @media (min-width: 640px) { .content { padding: var(--space-6); } }

        .asset-header-row {
          display: flex; justify-content: space-between; align-items: flex-start;
          gap: var(--space-4); flex-wrap: wrap; margin-bottom: var(--space-6);
        }
        .asset-header { min-width: 0; }
        .ticker { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-text-primary); overflow-wrap: anywhere; }
        .asset-name { font-size: var(--font-size-lg); color: var(--color-text-secondary); margin-top: var(--space-1); overflow-wrap: anywhere; }
        .asset-meta { display: flex; gap: var(--space-2); margin-top: var(--space-2); flex-wrap: wrap; }
        .badge {
          display: inline-block; padding: 2px var(--space-2);
          background: var(--color-bg-surface); border: 1px solid var(--color-border);
          border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--color-text-secondary);
        }
        @media (max-width: 639px) {
          .asset-header-row { flex-direction: column; align-items: stretch; }
        }

        .summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-6); }
        .summary-card {
          padding: var(--space-4); border: 1px solid var(--color-border);
          border-radius: var(--radius-md); background: var(--color-bg-secondary);
        }
        .summary-label { font-size: var(--font-size-xs); color: var(--color-text-secondary);
          margin-bottom: var(--space-1); text-transform: uppercase; letter-spacing: 0.05em; }
        .summary-value { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
        .summary-value.positive { color: var(--color-success); }
        .summary-value.negative { color: var(--color-danger); }
        .summary-sub { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: 2px; }

        .actions { display: flex; flex-wrap: wrap; gap: var(--space-2); justify-content: flex-end; }
        @media (max-width: 639px) { .actions { justify-content: flex-start; } }
        .btn { background: var(--color-accent); color: #fff; padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
        .btn:hover { background: var(--color-accent-hover); }
        .btn-outline { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); }
        .btn-outline:hover { background: var(--color-bg-surface); }
        .btn-danger { border: 1px solid var(--color-danger); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-danger); }
        .btn-danger:hover { background: var(--color-danger); color: #fff; }
        .btn-xs { padding: 1px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); border: 1px solid var(--color-border);
          color: var(--color-text-secondary); }
        .btn-xs:hover { background: var(--color-bg-surface); }
        .btn-xs-danger { padding: 1px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); border: 1px solid var(--color-danger); color: var(--color-danger); }
        .btn-xs-danger:hover { background: var(--color-danger); color: #fff; }
        .btn-xs-primary { padding: 1px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); background: var(--color-accent); color: #fff; }
        .lot-actions { display: flex; flex-direction: column; align-items: stretch; gap: 2px; }
        .lot-actions button { width: 100%; text-align: center; }

        .confirm-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); flex-wrap: wrap; }
        .confirm-label { color: var(--color-text-secondary); }

        .section { margin-bottom: var(--space-6); }
        .section-title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary); margin-bottom: var(--space-3);
          text-transform: uppercase; letter-spacing: 0.05em;
          display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
        .section-title-link { font-size: var(--font-size-xs); text-transform: none; letter-spacing: 0;
          color: var(--color-accent); font-weight: normal; cursor: pointer; }
        .section-title-link:hover { text-decoration: underline; }

        .boxed-section {
          border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); background: var(--color-bg-primary);
        }

        .alerts-section { margin-bottom: var(--space-6); }
        .asset-alert { border-left: 4px solid var(--color-warning); padding: var(--space-3) var(--space-4);
          margin-bottom: var(--space-3); background: var(--color-warning-light); border-radius: var(--radius-sm);
          display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
        .asset-alert-main { min-width: 0; }
        .asset-alert-title { font-weight: var(--font-weight-semibold); }
        .asset-alert-meta { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: 2px; }
        .asset-alert-actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
        .unread-dot { display: inline-block; width: 8px; height: 8px; border-radius: 999px;
          background: var(--color-danger, #d9534f); margin-right: var(--space-2); vertical-align: middle; }

        .table-wrap { overflow-x: auto; }
        .table { width: 100%; border-collapse: collapse; border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow: hidden; }
        .table th { background: var(--color-bg-secondary); padding: var(--space-2) var(--space-3);
          font-size: var(--font-size-xs); text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--color-text-muted); text-align: left; border-bottom: 1px solid var(--color-border); }
        .table th.num, .table td.num { text-align: right; font-variant-numeric: tabular-nums; }
        .table th.act { text-align: right; width: 80px; }
        .table td { padding: var(--space-3); border-bottom: 1px solid var(--color-border); font-size: var(--font-size-sm); }
        .table tr:last-child td { border-bottom: none; }
        .consumed { color: var(--color-text-muted); font-size: var(--font-size-xs); display: block; }

        .form-row { display: flex; gap: var(--space-2); flex-wrap: wrap; padding: var(--space-3);
          background: var(--color-bg-secondary); border-top: 1px solid var(--color-border); }
        .form-field { display: flex; flex-direction: column; gap: 2px; }
        .form-label { font-size: var(--font-size-xs); color: var(--color-text-secondary); }
        .form-input { border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          padding: 2px var(--space-2); font-size: var(--font-size-sm);
          background: var(--color-bg-primary); color: var(--color-text-primary); }
        .form-input:focus { border-color: var(--color-accent); outline: none; }
        .form-actions { display: flex; align-items: flex-end; gap: var(--space-2); }
        .form-error { color: var(--color-danger); font-size: var(--font-size-xs); padding: var(--space-1) var(--space-3); }

        .edit-td { background: var(--color-bg-secondary); }

        .indicator-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); }
        @media (min-width: 640px) { .indicator-grid { grid-template-columns: repeat(3, 1fr); } }
        .indicator-group {
          border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); background: var(--color-bg-primary);
        }
        .indicator-group + .indicator-group { margin-top: var(--space-4); }
        .indicator-group-title { font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
          color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.05em;
          margin-bottom: var(--space-3); }

        .empty-state { color: var(--color-text-muted); font-size: var(--font-size-sm); padding: var(--space-4); text-align: center;
          border: 1px dashed var(--color-border); border-radius: var(--radius-md); }
        .loading { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); padding: var(--space-4);
          border: 1px solid var(--color-danger); border-radius: var(--radius-sm); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="content">
        ${this._loading
          ? `<div class="loading">${t('common.loading')}</div>`
          : this._error
            ? `<div class="error-msg">${this._error}</div>`
            : h ? this._renderDetail(h) : `<div class="loading">${t('common.loading')}</div>`}
      </div>
    `;
  }

  private _fmt(date: string): string {
    return formatDate(date + 'T12:00:00');
  }

  private _renderAssetAlerts(quoteCurrency: string): string {
    const touchedLevels = this._priceLevels.filter((l) => l.status === 'touched');
    const dueAlerts = this._dateAlerts.filter((a) => a.status === 'due');
    if (touchedLevels.length === 0 && dueAlerts.length === 0) return '';

    return `
      <div class="alerts-section">
        <div class="section-title">${t('alerts.title')}</div>
        ${touchedLevels.map((l) => `
          <div class="asset-alert">
            <div class="asset-alert-main">
              <div class="asset-alert-title">
                ${l.alert_seen_at === null ? '<span class="unread-dot"></span>' : ''}
                ${formatCurrency(l.target_price, quoteCurrency)} ${t('screen.price_level.direction.' + l.direction)}
              </div>
              ${l.note ? `<div class="asset-alert-meta">${l.note}</div>` : ''}
              ${l.touched_at ? `<div class="asset-alert-meta">${formatDateTime(l.touched_at)}</div>` : ''}
            </div>
            <div class="asset-alert-actions">
              ${l.alert_seen_at === null
                ? `<button class="btn-xs" data-mark-level-id="${l.id}">${t('alerts.mark_read')}</button>`
                : `<span class="asset-alert-meta">${t('alerts.read')}</span>`}
              <button class="btn-xs-danger" data-dismiss-level-id="${l.id}">${t('alerts.dismiss')}</button>
            </div>
          </div>
        `).join('')}
        ${dueAlerts.map((al) => `
          <div class="asset-alert">
            <div class="asset-alert-main">
              <div class="asset-alert-title">
                ${al.alert_seen_at === null ? '<span class="unread-dot"></span>' : ''}
                ${this._fmt(al.alert_date)} — ${al.description}
              </div>
            </div>
            <div class="asset-alert-actions">
              ${al.alert_seen_at === null
                ? `<button class="btn-xs" data-mark-date-alert-id="${al.id}">${t('alerts.mark_read')}</button>`
                : `<span class="asset-alert-meta">${t('alerts.read')}</span>`}
              <button class="btn-xs-danger" data-dismiss-date-alert-id="${al.id}">${t('alerts.dismiss')}</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  private _renderEditAssetForm(a: { ticker: string; name: string; market: string | null }): string {
    const f = this._editAssetForm;
    const marketHint = a.market
      ? t('screen.asset.edit.ticker_hint_market', { market: a.market, example: `${f.ticker || a.ticker}` })
      : t('screen.asset.edit.ticker_hint_us');
    return `
      <div class="form-row" style="margin-bottom:var(--space-4);flex-direction:column;gap:var(--space-3);">
        <div style="font-size:var(--font-size-xs);color:var(--color-text-muted);background:var(--color-bg-secondary);
          border:1px solid var(--color-border);border-radius:var(--radius-sm);padding:var(--space-2) var(--space-3);line-height:1.6;">
          ⚠ ${t('screen.asset.edit.warning')}
          <br/><span style="color:var(--color-accent)">${marketHint}</span>
        </div>
        <div style="display:flex;gap:var(--space-3);flex-wrap:wrap;align-items:flex-end;">
          <div class="form-field">
            <label class="form-label">${t('screen.asset.edit.ticker')}</label>
            <input class="form-input" id="edit-asset-ticker" value="${f.ticker || a.ticker}" style="width:100px;text-transform:uppercase;" />
          </div>
          <div class="form-field">
            <label class="form-label">${t('screen.asset.edit.market')}</label>
            <input class="form-input" id="edit-asset-market" value="${f.market || a.market || ''}" style="width:90px;text-transform:uppercase;" />
          </div>
          <div class="form-field" style="flex:1;min-width:180px;">
            <label class="form-label">${t('screen.asset.edit.name')}</label>
            <input class="form-input" id="edit-asset-name" value="${f.name || a.name}" style="width:100%;" />
          </div>
          <div class="form-actions">
            <button class="btn-xs-primary" id="save-asset-btn">${t('common.button.save')}</button>
            <button class="btn-xs" id="cancel-edit-asset-btn">${t('common.button.cancel')}</button>
          </div>
        </div>
        ${this._editAssetError ? `<div class="form-error">${this._editAssetError}</div>` : ''}
      </div>
    `;
  }

  private _renderDetail(h: Holding): string {
    const a = h.asset;
    const agg = h.aggregates;
    const lots = h.lots ?? [];
    const sales = h.sales ?? [];
    const qty = Number(agg.quantity_held);
    const avgCost = Number(agg.avg_purchase_price_quote);
    const costBasis = qty * avgCost;

    const price = this._currentPrice;
    const priceStr = this._priceLoading
      ? `<span style="font-size:var(--font-size-sm);color:var(--color-text-muted)">${t('common.loading')}</span>`
      : price !== null
        ? formatNumber(price, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
        : `<span style="font-size:var(--font-size-sm);color:var(--color-text-muted)">${t('screen.asset.price_na')}</span>`;

    const marketValue = price !== null ? qty * price : null;
    const pl = marketValue !== null ? marketValue - costBasis : null;
    const plPct = pl !== null && costBasis > 0 ? (pl / costBasis) * 100 : null;
    const plClass = pl === null ? '' : pl >= 0 ? 'positive' : 'negative';
    const plSign = pl !== null && pl >= 0 ? '+' : '';

    const anyLotNotes = lots.some((l) => l.notes);
    const technicalIndicators = this._indicators.filter((ind) => ind.nature === 'technical');
    const fundamentalIndicators = this._indicators.filter((ind) => ind.nature === 'fundamental');

    return `
      <div class="asset-header-row">
        <div class="asset-header">
          <div class="ticker">${a.ticker}</div>
          <div class="asset-name">${a.name}</div>
          <div class="asset-meta">
            ${a.market ? `<span class="badge">${a.market}</span>` : ''}
            <span class="badge">${a.asset_type}</span>
            <span class="badge">${a.quote_currency}</span>
          </div>
        </div>
        <div class="actions">
          <button class="btn-outline" id="levels-btn">${t('screen.holding.alerts')}</button>
          <button class="btn-outline" id="analysis-btn">${t('screen.holding.analysis')}</button>
          <button class="btn-outline" id="edit-asset-btn">${t('screen.asset.edit_asset')}</button>
          <button class="btn-outline" id="back-btn">${t('common.button.back')}</button>
          ${this._confirmDeleteHolding
            ? `<div class="confirm-row">
                 <span class="confirm-label">${t('screen.holding.delete.confirm')}</span>
                 <button class="btn-danger" id="do-delete-holding-btn">${t('common.button.confirm')}</button>
                 <button class="btn-outline" id="cancel-delete-holding-btn">${t('common.button.cancel')}</button>
               </div>`
            : `<button class="btn-danger" id="delete-holding-btn">${t('screen.holding.delete')}</button>`}
        </div>
      </div>

      ${this._renderAssetAlerts(a.quote_currency)}

      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.quantity')}</div>
          <div class="summary-value">${formatNumber(qty, { maximumFractionDigits: 8 })}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.avg_cost')}</div>
          <div class="summary-value">${formatNumber(avgCost, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</div>
          <div class="summary-sub">${a.quote_currency} / ${t('screen.asset.unit')}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.current_price')}</div>
          <div class="summary-value">${priceStr}</div>
          <div class="summary-sub">${a.quote_currency}</div>
          ${this._priceFetchedAt ? `<div class="summary-sub">${formatDateTime(this._priceFetchedAt)}</div>` : ''}
        </div>
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.total_invested')}</div>
          <div class="summary-value">${formatNumber(costBasis, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          <div class="summary-sub">${a.quote_currency}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.market_value')}</div>
          <div class="summary-value">${marketValue !== null ? formatNumber(marketValue, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</div>
          <div class="summary-sub">${a.quote_currency}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">${t('screen.asset.unrealized_pl')}</div>
          <div class="summary-value ${plClass}">${pl !== null ? `${plSign}${formatNumber(pl, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}</div>
          ${plPct !== null ? `<div class="summary-sub">${plSign}${formatNumber(plPct, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</div>` : ''}
        </div>
      </div>

      ${this._editingAsset ? this._renderEditAssetForm(a) : ''}

      <div class="section boxed-section">
        <div class="section-title">
          ${t('screen.holding.lots')} · ${lots.length}
          <button class="btn-xs" id="add-lot-btn">${t('screen.holding.add_lot')}</button>
        </div>
        ${this._addingLot ? this._renderAddLotForm() : ''}
        ${lots.length === 0 && !this._addingLot
          ? `<div class="empty-state">${t('screen.holding.lots_empty')}</div>`
          : lots.length > 0
            ? `<div class="table-wrap"><table class="table">
                <thead><tr>
                  <th>${t('screen.lot.purchase_date')}</th>
                  <th class="num">${t('screen.lot.quantity')}</th>
                  <th class="num">${t('screen.lot.price')}</th>
                  <th class="num">Total</th>
                  ${anyLotNotes ? `<th>${t('screen.lot.notes')}</th>` : ''}
                  <th class="act"></th>
                </tr></thead>
                <tbody>
                  ${lots.map((l) => {
                    const lqty = Number(l.quantity);
                    const lconsumed = Number(l.quantity_consumed);
                    if (this._editLotId === l.id) return this._renderEditLotRow(l.id, anyLotNotes);
                    if (this._confirmDeleteLotId === l.id) {
                      const colspan = anyLotNotes ? 6 : 5;
                      return `<tr>
                        <td colspan="${colspan}">
                          <div class="confirm-row">
                            <span class="confirm-label">${t('screen.lot.delete.confirm')}</span>
                            <button class="btn-xs-danger" data-do-delete-lot="${l.id}">${t('common.button.confirm')}</button>
                            <button class="btn-xs" data-cancel-delete-lot="${l.id}">${t('common.button.cancel')}</button>
                            ${this._deleteLotError ? `<span style="color:var(--color-danger);font-size:var(--font-size-xs)">${this._deleteLotError}</span>` : ''}
                          </div>
                        </td>
                      </tr>`;
                    }
                    return `<tr>
                      <td>${this._fmt(l.purchase_date)}</td>
                      <td class="num">
                        ${formatNumber(lqty, { maximumFractionDigits: 8 })}
                        ${lconsumed > 0 ? `<span class="consumed">−${formatNumber(lconsumed, { maximumFractionDigits: 8 })} ${t('screen.lot.consumed')}</span>` : ''}
                      </td>
                      <td class="num">${formatNumber(Number(l.unit_price), { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                      <td class="num">${formatNumber(lqty * Number(l.unit_price), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      ${anyLotNotes ? `<td>${l.notes ?? ''}</td>` : ''}
                      <td class="num lot-actions">
                        <button class="btn-xs" data-edit-lot="${l.id}" data-lot-date="${l.purchase_date}" data-lot-qty="${l.quantity}" data-lot-price="${l.unit_price}" data-lot-notes="${l.notes ?? ''}">${t('common.button.edit')}</button>
                        <button class="btn-xs-danger" data-delete-lot="${l.id}">${t('common.button.delete')}</button>
                      </td>
                    </tr>`;
                  }).join('')}
                </tbody>
              </table></div>`
            : ''}
      </div>

      ${sales.length > 0 ? `
      <div class="section">
        <div class="section-title">${t('screen.holding.sales')} · ${sales.length}</div>
        <div class="table-wrap"><table class="table">
          <thead><tr>
            <th>${t('screen.sale.sale_date')}</th>
            <th class="num">${t('screen.sale.quantity')}</th>
            <th class="num">${t('screen.sale.price')}</th>
            <th class="num">Total</th>
          </tr></thead>
          <tbody>
            ${sales.map((s) => `<tr>
              <td>${this._fmt(s.sale_date)}</td>
              <td class="num">${formatNumber(Number(s.quantity), { maximumFractionDigits: 8 })}</td>
              <td class="num">${formatNumber(Number(s.unit_price), { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
              <td class="num">${formatNumber(Number(s.quantity) * Number(s.unit_price), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
            </tr>`).join('')}
          </tbody>
        </table></div>
      </div>
      ` : ''}

      ${this._indicators.length > 0 ? `
      <div class="section">
        <div class="section-title">
          ${t('screen.holding.indicators')}
          <span class="section-title-link" id="legend-link">${t('screen.holding.indicators_guide')}</span>
        </div>
        ${technicalIndicators.length > 0 ? `
          <div class="indicator-group">
            <div class="indicator-group-title">${t('screen.holding.indicators_technical')}</div>
            <div class="indicator-grid" id="indicators-grid-technical">
              ${technicalIndicators.map(() => '<pi-indicator-card></pi-indicator-card>').join('')}
            </div>
          </div>
        ` : ''}
        ${fundamentalIndicators.length > 0 ? `
          <div class="indicator-group">
            <div class="indicator-group-title">${t('screen.holding.indicators_fundamental')}</div>
            <div class="indicator-grid" id="indicators-grid-fundamental">
              ${fundamentalIndicators.map(() => '<pi-indicator-card></pi-indicator-card>').join('')}
            </div>
          </div>
        ` : ''}
      </div>
      ` : ''}
    `;
  }

  private _renderAddLotForm(): string {
    const f = this._addLotForm;
    return `
      <div class="form-row">
        <div class="form-field">
          <label class="form-label">${t('screen.lot.purchase_date')}</label>
          <input class="form-input" id="add-lot-date" type="date" value="${f.date}" />
        </div>
        <div class="form-field">
          <label class="form-label">${t('screen.lot.quantity')}</label>
          <input class="form-input" id="add-lot-qty" type="number" step="any" min="0" value="${f.qty}" style="width:90px" />
        </div>
        <div class="form-field">
          <label class="form-label">${t('screen.lot.price')}</label>
          <input class="form-input" id="add-lot-price" type="number" step="any" min="0" value="${f.price}" style="width:90px" />
        </div>
        <div class="form-field">
          <label class="form-label">${t('screen.lot.notes')}</label>
          <input class="form-input" id="add-lot-notes" type="text" value="${f.notes}" style="width:120px" />
        </div>
        <div class="form-actions">
          <button class="btn-xs-primary" id="add-lot-save-btn">${t('common.button.save')}</button>
          <button class="btn-xs" id="add-lot-cancel-btn">${t('common.button.cancel')}</button>
        </div>
      </div>
      ${this._addLotError ? `<div class="form-error">${this._addLotError}</div>` : ''}
    `;
  }

  private _renderEditLotRow(lotId: string, hasNotes: boolean): string {
    const f = this._editLotForm;
    const colspan = hasNotes ? 6 : 5;
    return `
      <tr class="edit-td">
        <td colspan="${colspan}">
          <div class="form-row" style="padding:0;background:none;border:none;">
            <div class="form-field">
              <label class="form-label">${t('screen.lot.purchase_date')}</label>
              <input class="form-input" id="edit-lot-date" type="date" value="${f.date}" />
            </div>
            <div class="form-field">
              <label class="form-label">${t('screen.lot.quantity')}</label>
              <input class="form-input" id="edit-lot-qty" type="number" step="any" min="0" value="${f.qty}" style="width:90px" />
            </div>
            <div class="form-field">
              <label class="form-label">${t('screen.lot.price')}</label>
              <input class="form-input" id="edit-lot-price" type="number" step="any" min="0" value="${f.price}" style="width:90px" />
            </div>
            <div class="form-field">
              <label class="form-label">${t('screen.lot.notes')}</label>
              <input class="form-input" id="edit-lot-notes" type="text" value="${f.notes}" style="width:120px" />
            </div>
            <div class="form-actions">
              <button class="btn-xs-primary" data-save-edit-lot="${lotId}">${t('common.button.save')}</button>
              <button class="btn-xs" id="cancel-edit-lot-btn">${t('common.button.cancel')}</button>
            </div>
          </div>
          ${this._editLotError ? `<div class="form-error">${this._editLotError}</div>` : ''}
        </td>
      </tr>
    `;
  }

  protected afterRender(): void {
    const pid = this._portfolioId, hid = this._holdingId;
    this.shadow.getElementById('levels-btn')?.addEventListener('click', () =>
      navigate(`/app/portfolios/${pid}/assets/${hid}/levels`));
    this.shadow.getElementById('analysis-btn')?.addEventListener('click', () =>
      navigate(`/app/portfolios/${pid}/assets/${hid}/analysis`));
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/app/portfolios/${pid}`));
    this.shadow.getElementById('legend-link')?.addEventListener('click', () =>
      navigate('/app/indicators/legend'));

    // Embedded Alertas section
    this.shadow.querySelectorAll<HTMLElement>('[data-mark-level-id]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await markAlertSeen(pid, hid, btn.dataset['markLevelId']!);
        void this._reloadAlerts();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-dismiss-level-id]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await deletePriceLevel(pid, hid, btn.dataset['dismissLevelId']!, this._currentPrice ?? undefined);
        void this._reloadAlerts();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-mark-date-alert-id]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await markDateAlertSeen(pid, hid, btn.dataset['markDateAlertId']!);
        void this._reloadAlerts();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-dismiss-date-alert-id]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await deleteDateAlert(pid, hid, btn.dataset['dismissDateAlertId']!);
        void this._reloadAlerts();
      });
    });

    // Delete holding
    this.shadow.getElementById('delete-holding-btn')?.addEventListener('click', () => {
      this._confirmDeleteHolding = true;
      this._rerender();
    });
    this.shadow.getElementById('do-delete-holding-btn')?.addEventListener('click', () => void this._doDeleteHolding());
    this.shadow.getElementById('cancel-delete-holding-btn')?.addEventListener('click', () => {
      this._confirmDeleteHolding = false;
      this._rerender();
    });

    // Add lot
    this.shadow.getElementById('add-lot-btn')?.addEventListener('click', () => {
      this._addingLot = !this._addingLot;
      this._addLotForm = emptyLotForm();
      this._addLotError = '';
      this._editLotId = null;
      this._rerender();
      this.shadow.querySelector<HTMLInputElement>('#add-lot-date')?.focus();
    });
    this.shadow.getElementById('add-lot-save-btn')?.addEventListener('click', () => void this._doAddLot());
    this.shadow.getElementById('add-lot-cancel-btn')?.addEventListener('click', () => {
      this._addingLot = false;
      this._addLotError = '';
      this._rerender();
    });
    this._bindFormInputs('add-lot-date', 'add-lot-qty', 'add-lot-price', 'add-lot-notes',
      (f) => { this._addLotForm = f; });

    // Edit lot
    this.shadow.querySelectorAll<HTMLElement>('[data-edit-lot]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._editLotId = btn.dataset['editLot']!;
        this._editLotForm = {
          date: btn.dataset['lotDate'] ?? '',
          qty: btn.dataset['lotQty'] ?? '',
          price: btn.dataset['lotPrice'] ?? '',
          notes: btn.dataset['lotNotes'] ?? '',
        };
        this._editLotError = '';
        this._addingLot = false;
        this._confirmDeleteLotId = null;
        this._rerender();
        this.shadow.querySelector<HTMLInputElement>('#edit-lot-date')?.focus();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-save-edit-lot]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doEditLot(btn.dataset['saveEditLot']!));
    });
    this.shadow.getElementById('cancel-edit-lot-btn')?.addEventListener('click', () => {
      this._editLotId = null;
      this._editLotError = '';
      this._rerender();
    });
    this._bindFormInputs('edit-lot-date', 'edit-lot-qty', 'edit-lot-price', 'edit-lot-notes',
      (f) => { this._editLotForm = f; });

    // Delete lot
    this.shadow.querySelectorAll<HTMLElement>('[data-delete-lot]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmDeleteLotId = btn.dataset['deleteLot']!;
        this._deleteLotError = '';
        this._editLotId = null;
        this._rerender();
      });
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-do-delete-lot]').forEach((btn) => {
      btn.addEventListener('click', () => void this._doDeleteLot(btn.dataset['doDeleteLot']!));
    });
    this.shadow.querySelectorAll<HTMLElement>('[data-cancel-delete-lot]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmDeleteLotId = null;
        this._deleteLotError = '';
        this._rerender();
      });
    });

    // Edit asset
    this.shadow.getElementById('edit-asset-btn')?.addEventListener('click', () => {
      this._editingAsset = !this._editingAsset;
      this._editAssetError = '';
      this._editAssetForm = { ticker: '', name: '', market: '' };
      this._rerender();
      this.shadow.querySelector<HTMLInputElement>('#edit-asset-ticker')?.focus();
    });
    this.shadow.getElementById('save-asset-btn')?.addEventListener('click', () => void this._doSaveAsset());
    this.shadow.getElementById('cancel-edit-asset-btn')?.addEventListener('click', () => {
      this._editingAsset = false;
      this._editAssetError = '';
      this._rerender();
    });
    ['edit-asset-ticker', 'edit-asset-market', 'edit-asset-name'].forEach((id) => {
      this.shadow.getElementById(id)?.addEventListener('input', () => {
        this._editAssetForm = {
          ticker: (this.shadow.getElementById('edit-asset-ticker') as HTMLInputElement)?.value ?? '',
          market: (this.shadow.getElementById('edit-asset-market') as HTMLInputElement)?.value ?? '',
          name:   (this.shadow.getElementById('edit-asset-name')   as HTMLInputElement)?.value ?? '',
        };
      });
    });
  }

  private _bindFormInputs(
    dateId: string, qtyId: string, priceId: string, notesId: string,
    setter: (f: LotForm) => void,
  ): void {
    const read = (): LotForm => ({
      date: (this.shadow.getElementById(dateId) as HTMLInputElement)?.value ?? '',
      qty: (this.shadow.getElementById(qtyId) as HTMLInputElement)?.value ?? '',
      price: (this.shadow.getElementById(priceId) as HTMLInputElement)?.value ?? '',
      notes: (this.shadow.getElementById(notesId) as HTMLInputElement)?.value ?? '',
    });
    [dateId, qtyId, priceId, notesId].forEach((id) => {
      this.shadow.getElementById(id)?.addEventListener('input', () => setter(read()));
    });
  }

  private async _doSaveAsset(): Promise<void> {
    if (!this._holding) return;
    const ticker = (this.shadow.getElementById('edit-asset-ticker') as HTMLInputElement)?.value.trim().toUpperCase();
    const market = (this.shadow.getElementById('edit-asset-market') as HTMLInputElement)?.value.trim().toUpperCase();
    const name   = (this.shadow.getElementById('edit-asset-name')   as HTMLInputElement)?.value.trim();
    if (!ticker || !name) {
      this._editAssetError = t('validation.required');
      this._rerender();
      return;
    }
    try {
      const updated = await updateAsset(this._holding.asset.id, { ticker, name, market });
      this._holding = { ...this._holding, asset: { ...this._holding.asset, ...updated } };
      this._editingAsset = false;
      this._editAssetError = '';
      this._rerender();
    } catch (ex) {
      this._editAssetError = (ex as Error).message;
      this._rerender();
    }
  }

  private async _doDeleteHolding(): Promise<void> {
    try {
      await deleteHolding(this._portfolioId, this._holdingId);
      navigate(`/app/portfolios/${this._portfolioId}`);
    } catch (ex) {
      this._error = (ex as Error).message;
      this._confirmDeleteHolding = false;
      this._rerender();
    }
  }

  private async _doAddLot(): Promise<void> {
    const f = this._addLotForm;
    if (!f.date || !f.qty || !f.price) {
      this._addLotError = t('validation.required');
      this._rerender();
      return;
    }
    const body: AddLotBody = {
      purchase_date: f.date,
      quantity: Number(f.qty),
      unit_price: Number(f.price),
      notes: f.notes || undefined,
      fx_rate_origin: 'auto',
    };
    try {
      await addLot(this._portfolioId, this._holdingId, body);
      this._addingLot = false;
      this._addLotForm = emptyLotForm();
      this._addLotError = '';
      await this._reloadHolding();
    } catch (ex) {
      this._addLotError = (ex as Error).message;
      this._rerender();
    }
  }

  private async _doEditLot(lotId: string): Promise<void> {
    const f = this._editLotForm;
    if (!f.date || !f.qty || !f.price) {
      this._editLotError = t('validation.required');
      this._rerender();
      return;
    }
    const body: Partial<AddLotBody> = {
      purchase_date: f.date,
      quantity: Number(f.qty),
      unit_price: Number(f.price),
      notes: f.notes || undefined,
    };
    try {
      await updateLot(this._portfolioId, this._holdingId, lotId, body);
      this._editLotId = null;
      this._editLotError = '';
      await this._reloadHolding();
    } catch (ex) {
      this._editLotError = (ex as Error).message;
      this._rerender();
    }
  }

  private async _doDeleteLot(lotId: string): Promise<void> {
    try {
      await deleteLot(this._portfolioId, this._holdingId, lotId);
      this._confirmDeleteLotId = null;
      this._deleteLotError = '';
      await this._reloadHolding();
    } catch (ex) {
      this._deleteLotError = (ex as Error).message;
      this._rerender();
    }
  }

  private _mountIndicatorCards(): void {
    this._mountIndicatorGroup('indicators-grid-technical', 'technical');
    this._mountIndicatorGroup('indicators-grid-fundamental', 'fundamental');
  }

  private _mountIndicatorGroup(gridId: string, nature: string): void {
    const grid = this.shadow.getElementById(gridId);
    if (!grid) return;
    const indicators = this._indicators.filter((ind) => ind.nature === nature);
    const cards = grid.querySelectorAll('pi-indicator-card') as NodeListOf<HTMLElement & {
      indicator: Indicator;
      snapshots: IndicatorSnapshotHistory['snapshots'];
    }>;
    cards.forEach((card, i) => {
      const ind = indicators[i];
      if (!ind) return;
      const history = this._indicatorHistories.find((h) => h.indicator.code === ind.code);
      card.indicator = ind;
      card.snapshots = history?.snapshots ?? [];
    });
  }
}

customElements.define('pi-asset-detail-screen', AssetDetailScreen);
