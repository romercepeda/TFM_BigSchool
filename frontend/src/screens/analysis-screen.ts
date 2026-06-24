import { BaseComponent } from '../components/common/base-component.js';
import '../components/pdf-uploader.js';
import { t } from '../i18n/i18n.js';
import { listReports } from '../api/analyses.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { AiReport } from '../api/types.js';
import { formatDateTime } from '../utils/format.js';

export class AnalysisScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _reports: AiReport[] = [];

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  private async _load(): Promise<void> {
    this._reports = await listReports(this._holdingId);
    this.shadow.innerHTML = this.render();
  }

  protected render(): string {
    const statusColor: Record<string, string> = {
      pending: 'var(--color-warning)', running: 'var(--color-accent)',
      succeeded: 'var(--color-success)', failed: 'var(--color-danger)',
    };
    return `
      <style>
        :host { display: block; padding: var(--space-6); max-width: 640px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        h3 { font-size: var(--font-size-base); color: var(--color-text-secondary); margin: var(--space-6) 0 var(--space-3); }
        .report { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-4); margin-bottom: var(--space-3); }
        .status { font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold); margin-bottom: var(--space-2); }
        .summary { font-size: var(--font-size-sm); color: var(--color-text-secondary); white-space: pre-wrap; }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-4); }
      </style>
      <h2>${t('analysis.title')}</h2>
      <pi-pdf-uploader id="uploader"></pi-pdf-uploader>
      <h3>${t('analysis.history')}</h3>
      ${this._reports.map((r) => `
        <div class="report">
          <div class="status" style="color:${statusColor[r.status] ?? 'inherit'}">${t('analysis.status.' + r.status)}</div>
          <div>${r.pdf_filename ?? ''} · ${r.completed_at ? formatDateTime(r.completed_at) : ''}</div>
          ${r.summary ? `<div class="summary">${r.summary}</div>` : ''}
          ${r.error_message ? `<div style="color:var(--color-danger);font-size:var(--font-size-sm)">${r.error_message}</div>` : ''}
        </div>
      `).join('')}
      <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
    `;
  }

  protected afterRender(): void {
    const uploader = this.shadow.getElementById('uploader') as HTMLElement & { holdingId: string };
    if (uploader) uploader.holdingId = this._holdingId;
    this.shadow.getElementById('uploader')?.addEventListener('upload-complete', () => void this._load());
    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/assets/${this._holdingId}`));
  }
}

customElements.define('pi-analysis-screen', AnalysisScreen);
