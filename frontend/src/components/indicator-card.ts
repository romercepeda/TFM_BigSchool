import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { formatNumber, formatDate } from '../utils/format.js';
import type { Indicator, IndicatorSnapshot } from '../api/types.js';

const TIP_WIDTH = 240;

export class IndicatorCard extends BaseComponent {
  private _indicator: Indicator | null = null;
  private _snapshots: IndicatorSnapshot[] = [];

  set indicator(value: Indicator) {
    this._indicator = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this._bindTooltip(); }
  }

  set snapshots(value: IndicatorSnapshot[]) {
    this._snapshots = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this._bindTooltip(); }
  }

  private _displayValue(ind: Indicator, snap: IndicatorSnapshot): string {
    if (ind.data_type === 'quantitative') {
      return snap.value_numeric != null ? formatNumber(snap.value_numeric) : '—';
    }
    return snap.value_text_display ?? snap.value_text ?? '—';
  }

  private _shortDate(isoDate: string): string {
    return formatDate(isoDate + 'T12:00:00', { day: 'numeric', month: 'short' });
  }

  protected render(): string {
    const ind = this._indicator;
    if (!ind) return '<style>:host{display:block}</style>';

    const snaps = this._snapshots;
    const current = snaps[0] ?? null;

    const zoneColor: Record<string, string> = {
      overbought: 'var(--color-danger)',
      bullish:    'var(--color-success)',
      bearish:    'var(--color-danger)',
      neutral:    'var(--color-text-muted)',
      positive:   'var(--color-success)',
      attention:  'var(--color-danger)',
    };
    const zc = zoneColor[current?.zone ?? ''] ?? 'var(--color-text-primary)';
    const displayValue = current ? this._displayValue(ind, current) : '—';

    // Tooltip content
    const tooltipKey = `indicator.${ind.code}.tooltip`;
    const tooltipDesc = t(tooltipKey);
    const tooltipText = tooltipDesc !== tooltipKey ? tooltipDesc : t(`indicator.${ind.code}.description`);
    const zoneMeaningKey = current?.zone ? `indicator.zone.${current.zone}.meaning` : '';
    const zoneMeaning = zoneMeaningKey ? t(zoneMeaningKey) : '';
    const fullTooltip = [tooltipText, zoneMeaning]
      .filter((s) => s && s !== zoneMeaningKey)
      .join('\n\n');

    // History: 2 previous snapshots. Values sourced from an AI analysis get a
    // native title= tooltip with the report's period name (C05 §8); values
    // from the scheduled daily job never show one (there's no "report" behind them).
    const prevSnaps = snaps.slice(1);
    const historyHtml = prevSnaps.length > 0
      ? `<div class="history">
          ${prevSnaps.map((s) => {
            const tooltip = s.source === 'ai_analysis'
              ? (s.source_report_name || t('indicator.card.tooltip.name_missing'))
              : '';
            const titleAttr = tooltip ? ` title="${tooltip}"` : '';
            return `
            <div class="hist-item"${titleAttr}>
              <div class="hist-date">${this._shortDate(s.as_of_date)}</div>
              <div class="hist-val" style="color:${zoneColor[s.zone ?? ''] ?? 'var(--color-text-muted)'}">${this._displayValue(ind, s)}</div>
            </div>
          `;
          }).join('')}
         </div>`
      : '';

    return `
      <style>
        :host { display: block; }
        .card {
          padding: var(--space-3) var(--space-4);
          border: 1px solid var(--color-border);
          border-radius: var(--radius-md);
          background: var(--color-bg-secondary);
        }
        .name-row {
          display: flex; align-items: center; gap: var(--space-1);
          margin-bottom: var(--space-1);
        }
        .name {
          font-size: var(--font-size-sm); color: var(--color-text-secondary);
          flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .tip-icon {
          flex-shrink: 0;
          display: inline-flex; align-items: center; justify-content: center;
          width: 15px; height: 15px; border-radius: 50%;
          border: 1px solid var(--color-text-muted);
          font-size: 10px; line-height: 1; color: var(--color-text-muted);
          cursor: help;
        }
        /* Tooltip box: position:fixed so JS can clamp it to the viewport */
        .tip-box {
          display: none;
          position: fixed;
          width: ${TIP_WIDTH}px;
          background: var(--color-bg-primary);
          border: 1px solid var(--color-border);
          border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3);
          font-size: var(--font-size-xs); color: var(--color-text-primary);
          white-space: pre-line; line-height: 1.45;
          z-index: 9999;
          box-shadow: 0 4px 12px rgba(0,0,0,.18);
          pointer-events: none;
        }
        .value { font-size: var(--font-size-lg); font-weight: var(--font-weight-bold); }
        .zone  { font-size: var(--font-size-xs); margin-top: 2px; }
        .unit  { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .history {
          display: flex; gap: var(--space-3); margin-top: var(--space-2);
          padding-top: var(--space-2); border-top: 1px solid var(--color-border);
        }
        .hist-item { display: flex; flex-direction: column; gap: 1px; }
        .hist-item[title] { cursor: help; }
        .hist-date { font-size: 10px; color: var(--color-text-muted); }
        .hist-val  { font-size: var(--font-size-xs); font-weight: var(--font-weight-medium); }
      </style>
      <div class="card">
        <div class="name-row">
          <div class="name">${ind.name}</div>
          ${fullTooltip ? `<div class="tip-icon" id="tip-icon">?</div>` : ''}
        </div>
        <div class="value" style="color:${zc}">${displayValue}</div>
        ${ind.unit ? `<div class="unit">${ind.unit}</div>` : ''}
        ${current?.zone ? `<div class="zone" style="color:${zc}">${t('indicator.zone.' + current.zone, { zone: current.zone })}</div>` : ''}
        ${historyHtml}
        ${fullTooltip ? `<div class="tip-box" id="tip-box">${fullTooltip}</div>` : ''}
      </div>
    `;
  }

  protected afterRender(): void {
    this._bindTooltip();
  }

  private _bindTooltip(): void {
    const icon = this.shadow.getElementById('tip-icon');
    const box  = this.shadow.getElementById('tip-box') as HTMLElement | null;
    if (!icon || !box) return;

    icon.addEventListener('mouseenter', () => {
      const rect = icon.getBoundingClientRect();
      const margin = 8;

      // Prefer above the icon; fall back to below if not enough room
      const spaceAbove = rect.top;
      const boxH = box.offsetHeight || 120; // estimate before first paint
      const top = spaceAbove > boxH + margin
        ? rect.top - boxH - 6
        : rect.bottom + 6;

      // Center horizontally on the icon, then clamp to viewport
      let left = rect.left + rect.width / 2 - TIP_WIDTH / 2;
      const maxLeft = window.innerWidth - TIP_WIDTH - margin;
      if (left > maxLeft) left = maxLeft;
      if (left < margin) left = margin;

      box.style.top  = `${top}px`;
      box.style.left = `${left}px`;
      box.style.display = 'block';
    });

    icon.addEventListener('mouseleave', () => {
      box.style.display = 'none';
    });
  }
}

customElements.define('pi-indicator-card', IndicatorCard);
