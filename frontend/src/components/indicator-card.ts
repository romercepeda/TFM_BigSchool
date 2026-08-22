import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { formatNumber, formatDate } from '../utils/format.js';
import { hasPermission } from '../state/auth-state.js';
import { setIndicatorManualValue } from '../api/indicators.js';
import type { Indicator, IndicatorSnapshot } from '../api/types.js';

const TIP_WIDTH = 240;

export class IndicatorCard extends BaseComponent {
  private _indicator: Indicator | null = null;
  private _snapshots: IndicatorSnapshot[] = [];
  // Post-v1: admin manual-override entry + trailing 3-year average.
  // assetId is only set for asset-scoped indicators (the only scope the
  // manual-override endpoint supports) — the edit affordance stays hidden
  // without it, even for an admin.
  private _assetId = '';
  private _avg3y: string | null = null;
  private _editingManual = false;
  private _manualDate = new Date().toISOString().slice(0, 10);
  private _manualValue = '';
  private _manualError = '';
  private _manualSaving = false;

  set indicator(value: Indicator) {
    this._indicator = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this.afterRender(); }
  }

  set snapshots(value: IndicatorSnapshot[]) {
    this._snapshots = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this.afterRender(); }
  }

  set assetId(value: string) {
    this._assetId = value;
  }

  set avg3y(value: string | null) {
    this._avg3y = value;
    if (this.shadow) { this.shadow.innerHTML = this.render(); this.afterRender(); }
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
    const displayValue = current ? this._displayValue(ind, current) : '—';
    const zone = current?.zone ?? null;
    // Manual-override edit affordance (post-v1, admin-only): only for
    // asset-scoped indicators (assetId set) — the manual-value endpoint
    // doesn't support portfolio-scoped indicators.
    const canEdit = this._assetId !== '' && hasPermission('indicator.manual_override');

    // Changeset C15: always show which period/date the current value belongs
    // to — the report period name for AI-derived fundamentals (e.g. "FY 2025"),
    // or the processing date for scheduled technical indicators.
    const currentPeriodLabel = current
      ? current.source_report_name || formatDate(current.as_of_date + 'T12:00:00', { dateStyle: 'medium' })
      : '';

    // Tooltip content
    const tooltipKey = `indicator.${ind.code}.tooltip`;
    const tooltipDesc = t(tooltipKey);
    const tooltipText = tooltipDesc !== tooltipKey ? tooltipDesc : t(`indicator.${ind.code}.description`);
    const zoneMeaningKey = zone ? `indicator.zone.${zone}.meaning` : '';
    const zoneMeaning = zoneMeaningKey ? t(zoneMeaningKey) : '';
    const fullTooltip = [tooltipText, zoneMeaning]
      .filter((s) => s && s !== zoneMeaningKey)
      .join('\n\n');

    // Zone pill: color + glyph (never color alone — colorblind accessibility, C07 §8).
    const zonePill = current
      ? `<div class="signal" data-zone="${zone ?? 'unknown'}">${t('zone.' + (zone ?? 'unknown'))}</div>`
      : '';

    // History: up to 2 previous snapshots. Values sourced from an AI analysis
    // show the report's period name (e.g. "FY 2024") instead of the snapshot's
    // as_of_date — same fallback-to-date rule as currentPeriodLabel above, so a
    // reader sees which analysis a historical value belongs to, not just when
    // the row happened to be processed.
    const prevSnaps = snaps.slice(1);
    const historyHtml = current
      ? prevSnaps.length > 0
        ? `<div class="history">
            ${prevSnaps.map((s) => {
              const label = s.source === 'ai_analysis' && s.source_report_name
                ? s.source_report_name
                : this._shortDate(s.as_of_date);
              return `
              <div class="hist-item">
                <div class="hist-date">${label}</div>
                <div class="hist-val">${this._displayValue(ind, s)}</div>
              </div>
            `;
            }).join('')}
           </div>`
        : `<div class="history history--empty">${t('indicator.history.empty')}</div>`
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
          box-shadow: var(--elevation-2);
          pointer-events: none;
        }
        .value-row { display: flex; align-items: baseline; gap: 4px; }
        .value {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-lg); font-weight: var(--font-weight-bold);
          color: var(--color-text-primary);
        }
        .unit  { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .period { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: 2px; }
        .signal {
          display: inline-flex; align-items: center; gap: 4px;
          margin-top: var(--space-1);
          border: 1px solid var(--color-border); border-radius: var(--radius-full);
          padding: 1px var(--space-2);
          font-size: var(--font-size-xs); font-weight: var(--font-weight-medium);
          color: var(--color-text-muted); background: transparent;
        }
        .signal::before { content: ''; }
        .signal[data-zone="positive"] {
          color: var(--zone-positive); border-color: var(--zone-positive-border); background: var(--zone-positive-bg);
        }
        .signal[data-zone="positive"]::before { content: var(--zone-positive-glyph); }
        .signal[data-zone="neutral"] {
          color: var(--zone-neutral); border-color: var(--zone-neutral-border); background: var(--zone-neutral-bg);
        }
        .signal[data-zone="neutral"]::before { content: var(--zone-neutral-glyph); }
        .signal[data-zone="attention"] {
          color: var(--zone-attention); border-color: var(--zone-attention-border); background: var(--zone-attention-bg);
        }
        .signal[data-zone="attention"]::before { content: var(--zone-attention-glyph); }
        .history {
          display: flex; gap: var(--space-3); margin-top: var(--space-2);
          padding-top: var(--space-2); border-top: 1px solid var(--color-border);
        }
        .history--empty { font-size: var(--font-size-xs); color: var(--color-text-muted); font-style: italic; }
        .hist-item { display: flex; flex-direction: column; gap: 1px; }
        .hist-date { font-size: 10px; color: var(--color-text-muted); }
        .hist-val  {
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-xs); font-weight: var(--font-weight-medium);
          color: var(--color-text-secondary);
        }
        .edit-icon-btn {
          flex-shrink: 0; border: none; background: transparent; cursor: pointer;
          color: var(--color-text-muted); font-size: var(--font-size-xs); padding: 0 2px; opacity: 0.6;
        }
        .edit-icon-btn:hover { opacity: 1; color: var(--color-accent); }
        .manual-badge {
          font-size: 10px; color: var(--color-text-muted); font-style: italic;
          margin-left: var(--space-1);
        }
        .avg-line { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: 2px; }
        .manual-form {
          margin-top: var(--space-2); padding-top: var(--space-2); border-top: 1px solid var(--color-border);
          display: flex; flex-direction: column; gap: var(--space-1);
        }
        .manual-form input {
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          padding: 2px var(--space-2); font-size: var(--font-size-xs);
          background: var(--color-bg-primary); color: var(--color-text-primary);
        }
        .manual-actions { display: flex; gap: var(--space-2); }
        .manual-actions button {
          font-size: var(--font-size-xs); padding: 1px var(--space-2); border-radius: var(--radius-sm);
          border: 1px solid var(--color-border); color: var(--color-text-secondary); cursor: pointer;
        }
        .manual-actions button:first-child { background: var(--color-accent); color: #fff; border-color: var(--color-accent); }
        .manual-error { font-size: 10px; color: var(--color-danger); }
      </style>
      <div class="card">
        <div class="name-row">
          <div class="name">${t(ind.name_key)}</div>
          ${fullTooltip ? `<div class="tip-icon" id="tip-icon">?</div>` : ''}
        </div>
        <div class="value-row">
          <div class="value">${displayValue}</div>
          ${ind.unit ? `<div class="unit">${ind.unit}</div>` : ''}
          ${canEdit && !this._editingManual ? `<button class="edit-icon-btn" id="edit-manual-btn" title="${t('indicator.manual.edit')}">✎</button>` : ''}
        </div>
        ${currentPeriodLabel ? `<div class="period">${currentPeriodLabel}${current?.source === 'manual_override' ? `<span class="manual-badge">${t('indicator.manual.badge')}</span>` : ''}</div>` : ''}
        ${this._avg3y != null && ind.nature === 'fundamental'
          ? `<div class="avg-line">${t('indicator.avg_3y.label')}: ${formatNumber(Number(this._avg3y))}</div>`
          : ''}
        ${zonePill}
        ${historyHtml}
        ${this._editingManual ? `
          <div class="manual-form">
            <input type="date" id="manual-date" value="${this._manualDate}" />
            <input
              type="${ind.data_type === 'quantitative' ? 'number' : 'text'}"
              id="manual-value" step="any" value="${this._manualValue}"
              placeholder="${t('indicator.manual.value')}"
            />
            <div class="manual-actions">
              <button id="manual-save-btn" ${this._manualSaving ? 'disabled' : ''}>${t('common.button.save')}</button>
              <button id="manual-cancel-btn">${t('common.button.cancel')}</button>
            </div>
            ${this._manualError ? `<div class="manual-error">${this._manualError}</div>` : ''}
          </div>
        ` : ''}
        ${fullTooltip ? `<div class="tip-box" id="tip-box">${fullTooltip}</div>` : ''}
      </div>
    `;
  }

  protected afterRender(): void {
    this._bindTooltip();
    this._bindManualForm();
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

  // ── Manual override (post-v1, admin-only) ────────────────────────────────

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  private _bindManualForm(): void {
    this.shadow.getElementById('edit-manual-btn')?.addEventListener('click', () => {
      this._editingManual = true;
      this._manualDate = new Date().toISOString().slice(0, 10);
      this._manualValue = '';
      this._manualError = '';
      this._rerender();
      this.shadow.querySelector<HTMLInputElement>('#manual-value')?.focus();
    });
    this.shadow.getElementById('manual-cancel-btn')?.addEventListener('click', () => {
      this._editingManual = false;
      this._manualError = '';
      this._rerender();
    });
    this.shadow.getElementById('manual-date')?.addEventListener('input', () => {
      this._manualDate = (this.shadow.getElementById('manual-date') as HTMLInputElement)?.value ?? '';
    });
    this.shadow.getElementById('manual-value')?.addEventListener('input', () => {
      this._manualValue = (this.shadow.getElementById('manual-value') as HTMLInputElement)?.value ?? '';
    });
    this.shadow.getElementById('manual-save-btn')?.addEventListener('click', () => void this._doSaveManual());
  }

  private async _doSaveManual(): Promise<void> {
    const ind = this._indicator;
    if (!ind || !this._assetId || !this._manualDate || !this._manualValue.trim()) {
      this._manualError = t('validation.required');
      this._rerender();
      return;
    }
    this._manualSaving = true;
    this._manualError = '';
    this._rerender();
    try {
      await setIndicatorManualValue(this._assetId, ind.id, {
        as_of_date: this._manualDate,
        ...(ind.data_type === 'quantitative'
          ? { value_numeric: Number(this._manualValue) }
          : { value_text: this._manualValue.trim() }),
      });
      this._editingManual = false;
      this._manualSaving = false;
      // Parent screen owns the actual data (indicator + snapshots come from
      // a batch fetch it made) — ask it to reload rather than guessing a
      // merged local state here.
      this.dispatchEvent(new CustomEvent('indicator-updated', { bubbles: true, composed: true }));
    } catch (ex) {
      this._manualSaving = false;
      this._manualError = (ex as Error).message;
      this._rerender();
    }
  }
}

customElements.define('pi-indicator-card', IndicatorCard);
