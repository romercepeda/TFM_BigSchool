import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { formatNumber } from '../utils/format.js';
import type { Indicator, IndicatorSnapshot } from '../api/types.js';

export class IndicatorCard extends BaseComponent {
  private _indicator: Indicator | null = null;
  private _snapshot: IndicatorSnapshot | null = null;

  set indicator(value: Indicator) {
    this._indicator = value;
    if (this.shadow) this.shadow.innerHTML = this.render();
  }

  set snapshot(value: IndicatorSnapshot | null) {
    this._snapshot = value;
    if (this.shadow) this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    const ind = this._indicator;
    const snap = this._snapshot;
    if (!ind) return '<style>:host{display:block}</style>';

    const displayValue = snap
      ? (ind.data_type === 'quantitative'
          ? (snap.value_numeric != null ? formatNumber(snap.value_numeric) : '—')
          : (snap.value_text_display ?? snap.value_text ?? '—'))
      : '—';

    const zoneColor: Record<string, string> = {
      overbought: 'var(--color-danger)',
      bullish: 'var(--color-success)',
      bearish: 'var(--color-danger)',
      neutral: 'var(--color-text-muted)',
    };
    const zc = zoneColor[snap?.zone ?? ''] ?? 'var(--color-text-primary)';

    return `
      <style>
        :host { display: block; }
        .card {
          padding: var(--space-4); border: 1px solid var(--color-border);
          border-radius: var(--radius-md); background: var(--color-bg-secondary);
        }
        .name  { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-1); }
        .value { font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); }
        .zone  { font-size: var(--font-size-xs); margin-top: var(--space-1); }
        .unit  { font-size: var(--font-size-xs); color: var(--color-text-muted); }
      </style>
      <div class="card">
        <div class="name">${ind.name}</div>
        <div class="value" style="color:${zc}">${displayValue}</div>
        ${ind.unit ? `<div class="unit">${ind.unit}</div>` : ''}
        ${snap?.zone ? `<div class="zone" style="color:${zc}">${t('indicator.zone.' + snap.zone, { zone: snap.zone })}</div>` : ''}
      </div>
    `;
  }
}

customElements.define('pi-indicator-card', IndicatorCard);
