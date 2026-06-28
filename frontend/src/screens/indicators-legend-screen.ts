import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import { t } from '../i18n/i18n.js';
import { listIndicators } from '../api/indicators.js';
import type { Indicator } from '../api/types.js';

export class IndicatorsLegendScreen extends BaseComponent {
  private _indicators: Indicator[] = [];
  private _loading = true;
  private _error = '';

  connectedCallback(): void {
    super.connectedCallback();
    void this._load();
  }

  private async _load(): Promise<void> {
    this._loading = true;
    this.shadow.innerHTML = this.render();
    try {
      this._indicators = await listIndicators();
    } catch (ex) {
      this._error = (ex as Error).message;
    }
    this._loading = false;
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .content { padding: var(--space-6); max-width: 760px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        .section { margin-bottom: var(--space-8); }
        .section-title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-secondary);
          margin-bottom: var(--space-4); padding-bottom: var(--space-2);
          border-bottom: 1px solid var(--color-border); }
        .indicator { margin-bottom: var(--space-6); }
        .ind-name { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold);
          color: var(--color-text-primary); margin-bottom: var(--space-1); }
        .ind-desc { font-size: var(--font-size-sm); color: var(--color-text-secondary);
          margin-bottom: var(--space-3); }
        .zones-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
        .zones-table th { background: var(--color-bg-secondary); padding: var(--space-2) var(--space-3);
          text-align: left; color: var(--color-text-muted); font-size: var(--font-size-xs);
          text-transform: uppercase; border-bottom: 1px solid var(--color-border); }
        .zones-table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-border); }
        .zones-table tr:last-child td { border-bottom: none; }
        .zone-badge { display: inline-block; padding: 1px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); }
        .zone-positive { color: var(--color-success); }
        .zone-attention { color: var(--color-danger); }
        .zone-neutral { color: var(--color-text-secondary); }
        .info-note { font-size: var(--font-size-sm); color: var(--color-text-muted);
          font-style: italic; padding: var(--space-3); border: 1px dashed var(--color-border);
          border-radius: var(--radius-sm); }
        .categorical-list { list-style: none; padding: 0; margin: 0; font-size: var(--font-size-sm); }
        .categorical-list li { padding: var(--space-1) 0; display: flex; align-items: center; gap: var(--space-2); }
        .prose { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-bottom: var(--space-6); }
        .loading { color: var(--color-text-muted); padding: var(--space-8); text-align: center; }
        .error-msg { color: var(--color-danger); padding: var(--space-4);
          border: 1px solid var(--color-danger); border-radius: var(--radius-sm); }
      </style>
      <pi-header-bar></pi-header-bar>
      <div class="content">
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
        <h2>${t('screen.indicator_legend.title')}</h2>
        ${this._loading
          ? `<div class="loading">${t('common.loading')}</div>`
          : this._error
            ? `<div class="error-msg">${this._error}</div>`
            : this._renderSections()}
      </div>
    `;
  }

  private _renderSections(): string {
    const technical   = this._indicators.filter((i) => i.nature === 'technical');
    const fundamental = this._indicators.filter((i) => i.nature === 'fundamental');
    const kpis        = this._indicators.filter((i) => i.nature === 'portfolio_kpi');

    return `
      ${technical.length > 0 ? `
        <div class="section">
          <div class="section-title">${t('screen.indicator_legend.section_technical')}</div>
          ${technical.map((i) => this._renderIndicator(i)).join('')}
        </div>` : ''}
      ${fundamental.length > 0 ? `
        <div class="section">
          <div class="section-title">${t('screen.indicator_legend.section_fundamental')}</div>
          ${fundamental.map((i) => this._renderIndicator(i)).join('')}
        </div>` : ''}
      ${kpis.length > 0 ? `
        <div class="section">
          <div class="section-title">${t('screen.indicator_legend.section_kpis')}</div>
          ${kpis.map((i) => this._renderIndicator(i)).join('')}
        </div>` : ''}
    `;
  }

  private _renderIndicator(ind: Indicator): string {
    const descKey = `indicator.${ind.code}.description`;
    const desc = t(descKey);
    const cfg = ind.threshold_config as Record<string, unknown>;
    const model = cfg['model'] as string | undefined;

    return `
      <div class="indicator">
        <div class="ind-name">${ind.name}${ind.unit ? ` (${ind.unit})` : ''}</div>
        <div class="ind-desc">${desc !== descKey ? desc : ''}</div>
        ${this._renderZones(model, cfg)}
      </div>
    `;
  }

  private _renderZones(model: string | undefined, cfg: Record<string, unknown>): string {
    switch (model) {
      case 'numeric_thresholds': return this._renderNumericThresholds(cfg);
      case 'three_band_numeric':  return this._renderThreeBandNumeric(cfg);
      case 'categorical_state':   return this._renderCategoricalState(cfg);
      case 'price_vs_reference':  return this._renderPriceVsReference(cfg);
      case 'signed_with_trend':   return this._renderSignedWithTrend(cfg);
      case 'informational_only':
      default:
        return `<div class="info-note">${t('screen.indicator_legend.informational_only_note')}</div>`;
    }
  }

  private _fmt(band: Record<string, unknown> | null | undefined): string {
    if (!band) return '—';
    const min = band['min'] as number | null;
    const max = band['max'] as number | null;
    if (min !== null && min !== undefined && max !== null && max !== undefined) return `${min} – ${max}`;
    if (min !== null && min !== undefined) return `≥ ${min}`;
    if (max !== null && max !== undefined) return `< ${max}`;
    return '—';
  }

  private _renderNumericThresholds(cfg: Record<string, unknown>): string {
    const rows = [
      { zone: 'positive', label: t('screen.indicator_legend.zone_positive'), cls: 'zone-positive', band: cfg['positive'] },
      { zone: 'neutral',  label: t('screen.indicator_legend.zone_neutral'),  cls: 'zone-neutral',  band: cfg['neutral'] },
      { zone: 'attention',label: t('screen.indicator_legend.zone_attention'),cls: 'zone-attention', band: cfg['attention'] },
    ] as const;
    return `
      <table class="zones-table">
        <thead><tr><th>${t('screen.indicator_legend.zone_positive').replace('Positivo','Zona').replace('Positive','Zone')}</th><th>Rango</th></tr></thead>
        <tbody>
          ${rows.map((r) => `<tr>
            <td><span class="${r.cls}">${r.label}</span></td>
            <td>${this._fmt(r.band as Record<string, unknown>)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  private _renderThreeBandNumeric(cfg: Record<string, unknown>): string {
    const bands = [
      { key: 'attention_low',  label: t('screen.indicator_legend.zone_attention') + ' (bajo)', cls: 'zone-attention' },
      { key: 'neutral_low',    label: t('screen.indicator_legend.zone_neutral') + ' (bajo)',   cls: 'zone-neutral' },
      { key: 'positive',       label: t('screen.indicator_legend.zone_positive'),              cls: 'zone-positive' },
      { key: 'neutral_high',   label: t('screen.indicator_legend.zone_neutral') + ' (alto)',   cls: 'zone-neutral' },
      { key: 'attention_high', label: t('screen.indicator_legend.zone_attention') + ' (alto)', cls: 'zone-attention' },
    ] as const;
    return `
      <table class="zones-table">
        <thead><tr><th>Zona</th><th>Rango</th></tr></thead>
        <tbody>
          ${bands.map((b) => `<tr>
            <td><span class="${b.cls}">${b.label}</span></td>
            <td>${this._fmt(cfg[b.key] as Record<string, unknown>)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  private _renderCategoricalState(cfg: Record<string, unknown>): string {
    const mapping = cfg['mapping'] as Record<string, string> | undefined;
    if (!mapping) return '';
    const zoneClass: Record<string, string> = {
      positive:  'zone-positive',
      neutral:   'zone-neutral',
      attention: 'zone-attention',
    };
    const zoneLabel: Record<string, string> = {
      positive:  t('screen.indicator_legend.zone_positive'),
      neutral:   t('screen.indicator_legend.zone_neutral'),
      attention: t('screen.indicator_legend.zone_attention'),
    };
    const zoneOrder: Record<string, number> = { positive: 0, neutral: 1, attention: 2 };
    const rows = Object.entries(mapping)
      .sort(([, za], [, zb]) => (zoneOrder[za] ?? 9) - (zoneOrder[zb] ?? 9));
    return `
      <ul class="categorical-list">
        ${rows.map(([state, zone]) => `
          <li>
            <span class="${zoneClass[zone] ?? ''}">${zoneLabel[zone] ?? zone}</span>
            <span style="color:var(--color-text-muted)">←</span>
            <span>${t('indicator.state.' + state)}</span>
          </li>
        `).join('')}
      </ul>`;
  }

  private _renderPriceVsReference(cfg: Record<string, unknown>): string {
    const band = Number(cfg['neutral_band_pct'] ?? 0.02) * 100;
    return `
      <div class="prose">
        <span class="zone-positive">${t('screen.indicator_legend.zone_positive')}</span>: precio &gt; MA × ${(1 + Number(cfg['neutral_band_pct'] ?? 0.02)).toFixed(2)}<br/>
        <span class="zone-attention">${t('screen.indicator_legend.zone_attention')}</span>: precio &lt; MA × ${(1 - Number(cfg['neutral_band_pct'] ?? 0.02)).toFixed(2)}<br/>
        <span class="zone-neutral">${t('screen.indicator_legend.zone_neutral')}</span>: banda ±${band.toFixed(0)}% alrededor de la MA
      </div>`;
  }

  private _renderSignedWithTrend(cfg: Record<string, unknown>): string {
    const threshold = cfg['near_zero_threshold'] ?? 0.5;
    return `
      <div class="prose">
        <span class="zone-neutral">${t('screen.indicator_legend.zone_neutral')}</span>: |valor| ≤ ${threshold}<br/>
        <span class="zone-positive">${t('screen.indicator_legend.zone_positive')}</span>: valor &gt; 0 y subiendo<br/>
        <span class="zone-attention">${t('screen.indicator_legend.zone_attention')}</span>: valor &lt; 0 y bajando
      </div>`;
  }

  protected afterRender(): void {
    this.shadow.getElementById('back-btn')?.addEventListener('click', () => history.back());
  }
}

customElements.define('pi-indicators-legend-screen', IndicatorsLegendScreen);
