import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';

// Portfolio performance KPIs (TWR/CAGR/Max drawdown/Volatility/Sharpe) are not
// computed yet (C07 §6, §8) — this strip shows an honest pending state instead
// of fabricating values. Wire real figures here once the daily close job
// calculates them.
const KPI_LABEL_KEYS = [
  'screen.dashboard.kpi.twr',
  'screen.dashboard.kpi.cagr',
  'screen.dashboard.kpi.max_drawdown',
  'screen.dashboard.kpi.volatility',
  'screen.dashboard.kpi.sharpe',
] as const;

export class KpiStrip extends BaseComponent {
  protected render(): string {
    return `
      <style>
        :host { display: block; }
        :host { display: block; margin-bottom: var(--space-6); }
        .section-label {
          font-size: var(--font-size-xs); color: var(--color-text-muted);
          text-transform: uppercase; letter-spacing: 0.05em;
          padding: var(--space-3) var(--space-4) 0;
          border: 1px solid var(--color-border); border-bottom: none;
          border-radius: var(--radius-md) var(--radius-md) 0 0;
          background: var(--color-bg-secondary);
        }
        .strip {
          display: flex; gap: var(--space-4); flex-wrap: wrap;
          padding: var(--space-2) var(--space-4) var(--space-3);
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border); border-top: none;
          border-radius: 0 0 var(--radius-md) var(--radius-md);
        }
        .kpi { display: flex; flex-direction: column; gap: 2px; opacity: 0.7; }
        .label { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .value {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-base); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary);
        }
        .hint { font-size: 10px; color: var(--color-text-muted); font-style: italic; }
      </style>
      <div class="section-label">${t('screen.dashboard.kpi.section')}</div>
      <div class="strip">
        ${KPI_LABEL_KEYS.map((labelKey) => `
          <div class="kpi">
            <span class="label">${t(labelKey)}</span>
            <span class="value">${t('screen.dashboard.kpi.pending')}</span>
            <span class="hint">${t('screen.dashboard.kpi.pending_hint')}</span>
          </div>
        `).join('')}
      </div>
    `;
  }
}

customElements.define('pi-kpi-strip', KpiStrip);
