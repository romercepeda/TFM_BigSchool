import { BaseComponent } from '../components/common/base-component.js';
import '../components/pdf-uploader.js';
import { t } from '../i18n/i18n.js';
import { listReports, getReport, deleteReport, getJobs } from '../api/analyses.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import type { AiReportSummary, AiReportDetail } from '../api/types.js';

export class AnalysisScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _reports: AiReportSummary[] = [];
  private _expandedId: string | null = null;
  private _expandedDetail: AiReportDetail | null = null;
  private _confirmDeleteId: string | null = null;
  private _error = '';

  // Job tracking state
  private _jobId: string | null = null;
  private _jobStatus: string | null = null;
  private _jobAttemptCount = 0;
  private _jobError: string | null = null;
  private _jobResult: AiReportDetail | null = null;
  private _pollTimer: ReturnType<typeof setInterval> | null = null;
  private _pollStartedAt: number | null = null;
  private static readonly _POLL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes

  set params(p: RouteParams) {
    this._portfolioId = p['portfolioId'] ?? '';
    this._holdingId   = p['holdingId'] ?? '';
    void this._load();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._stopPolling();
  }

  private async _load(): Promise<void> {
    try {
      this._reports = await listReports(this._portfolioId, this._holdingId);
    } catch {
      this._error = t('common.error.generic');
    }
    this._rerender();
  }

  private _rerender(): void {
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  // ── Job polling ─────────────────────────────────────────────────────────────

  private _startPolling(): void {
    if (this._pollTimer !== null) return;
    this._pollStartedAt = Date.now();
    this._pollTimer = setInterval(() => void this._pollJob(), 3000);
  }

  private _stopPolling(): void {
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  private async _pollJob(): Promise<void> {
    if (!this._jobId) return;

    // Frontend timeout: if the job takes too long, show a warning but keep polling
    const elapsed = this._pollStartedAt ? Date.now() - this._pollStartedAt : 0;
    if (elapsed > AnalysisScreen._POLL_TIMEOUT_MS) {
      this._stopPolling();
      this._jobStatus = 'timeout';
      this._rerender();
      return;
    }

    try {
      const jobs = await getJobs();
      const job = jobs.find((j) => j.id === this._jobId);
      if (!job) return; // not yet visible in job list, keep polling

      const prevAttempt = this._jobAttemptCount;
      const prevStatus = this._jobStatus;
      this._jobStatus = job.status;
      this._jobAttemptCount = job.attempt_count ?? 0;
      this._jobError = job.last_error ?? null;

      if (job.status === 'succeeded' && job.analysis_report_id) {
        this._stopPolling();
        try {
          this._jobResult = await getReport(job.analysis_report_id);
        } catch {
          this._jobResult = null;
        }
        await this._load(); // reloads reports list and rerenders
      } else if (job.status === 'failed') {
        this._stopPolling();
        this._rerender();
      } else if (job.status !== prevStatus || this._jobAttemptCount !== prevAttempt) {
        this._rerender();
      }
    } catch {
      // network error — keep polling silently
    }
  }

  private _dismissJob(): void {
    this._stopPolling();
    this._jobId = null;
    this._jobStatus = null;
    this._jobAttemptCount = 0;
    this._jobError = null;
    this._jobResult = null;
    this._pollStartedAt = null;
    this._rerender();
  }

  // ── Render helpers ───────────────────────────────────────────────────────────

  private _signalColor(signal: string | null): string {
    if (signal === 'bullish') return 'var(--color-success)';
    if (signal === 'bearish') return 'var(--color-danger)';
    return 'var(--color-warning)';
  }

  private _signalLabel(signal: string | null): string {
    if (signal === 'bullish') return t('analysis.global_signal.bullish');
    if (signal === 'bearish') return t('analysis.global_signal.bearish');
    if (signal === 'neutral') return t('analysis.global_signal.neutral');
    return '—';
  }

  private _formatMetric(key: string, value: number | string | null): string {
    if (value === null || value === undefined) return '—';
    if (key === 'roe' || key === 'revenue_growth_yoy') {
      const pct = Number(value) * 100;
      return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
    }
    if (key === 'analyst_sentiment') return String(value);
    return Number(value).toFixed(2);
  }

  private _renderMetrics(m: AiReportDetail['extracted_metrics']): string {
    const rows: [string, string][] = [
      ['PER', this._formatMetric('per', m.per)],
      ['ROE', this._formatMetric('roe', m.roe)],
      ['Deuda/EBITDA', this._formatMetric('debt_ebitda', m.debt_ebitda)],
      ['Rev. Growth YoY', this._formatMetric('revenue_growth_yoy', m.revenue_growth_yoy)],
      [t('analysis.analyst_sentiment'), this._formatMetric('analyst_sentiment', m.analyst_sentiment)],
    ];
    return `<div class="metrics-grid">${rows.map(([label, val]) =>
      `<div class="metric-cell"><span class="metric-label">${label}</span><span class="metric-val">${val}</span></div>`
    ).join('')}</div>`;
  }

  private _renderUpdatedIndicators(m: AiReportDetail['extracted_metrics'], signal: string | null): string {
    const items: string[] = [];
    if (signal) items.push(`<span class="indicator-chip signal" style="border-color:${this._signalColor(signal)};color:${this._signalColor(signal)}">${t('analysis.global_signal')}: ${this._signalLabel(signal)}</span>`);
    if (m.per !== null) items.push(`<span class="indicator-chip">PER: ${this._formatMetric('per', m.per)}</span>`);
    if (m.roe !== null) items.push(`<span class="indicator-chip">ROE: ${this._formatMetric('roe', m.roe)}</span>`);
    if (m.debt_ebitda !== null) items.push(`<span class="indicator-chip">Deuda/EBITDA: ${this._formatMetric('debt_ebitda', m.debt_ebitda)}</span>`);
    if (m.revenue_growth_yoy !== null) items.push(`<span class="indicator-chip">Rev. Growth YoY: ${this._formatMetric('revenue_growth_yoy', m.revenue_growth_yoy)}</span>`);
    if (m.analyst_sentiment !== null) items.push(`<span class="indicator-chip">${t('analysis.analyst_sentiment')}: ${this._formatMetric('analyst_sentiment', m.analyst_sentiment)}</span>`);
    if (items.length === 0) return '';
    return `<div class="indicator-chips">${items.join('')}</div>`;
  }

  private _renderJobPanel(): string {
    if (!this._jobId) return '';

    if (this._jobStatus === 'failed') {
      const reason = this._jobError
        ? this._truncateError(this._jobError)
        : null;
      return `
        <div class="job-panel job-panel--error">
          <div class="job-panel__icon">✕</div>
          <div class="job-panel__message">${t('analysis.job.failed')}</div>
          ${reason ? `<div class="job-panel__error-detail">${t('analysis.job.failed_reason').replace('{reason}', reason)}</div>` : ''}
          <button class="btn-sm dismiss-btn">${t('analysis.result.dismiss')}</button>
        </div>
      `;
    }

    if (this._jobStatus === 'timeout') {
      return `
        <div class="job-panel job-panel--warning">
          <div class="job-panel__icon">⏱</div>
          <div class="job-panel__message">${t('analysis.processing.timeout')}</div>
          <button class="btn-sm dismiss-btn">${t('analysis.result.dismiss')}</button>
        </div>
      `;
    }

    if (this._jobStatus === 'succeeded' && !this._jobResult) {
      return `
        <div class="job-panel job-panel--success">
          <div class="job-panel__message">${t('analysis.result.title')}</div>
          <div class="job-panel__hint">${t('analysis.history')}</div>
          <button class="btn-sm dismiss-btn">${t('analysis.result.dismiss')}</button>
        </div>
      `;
    }

    if (this._jobResult && this._jobStatus === 'succeeded') {
      const r = this._jobResult;
      return `
        <div class="job-panel job-panel--success">
          <div class="job-panel__header">
            ${r.global_signal ? `<span class="signal-badge" style="background:${this._signalColor(r.global_signal)}">${this._signalLabel(r.global_signal)}</span>` : ''}
            <span class="job-panel__title">${t('analysis.result.title')}</span>
          </div>
          ${r.executive_summary ? `<div class="job-panel__summary">${r.executive_summary}</div>` : ''}
          <div class="job-panel__section-label">${t('analysis.result.indicators_updated')}</div>
          ${this._renderUpdatedIndicators(r.extracted_metrics, r.global_signal)}
          ${r.confidence_notes ? `<div class="job-panel__confidence">${t('analysis.confidence_notes')}: ${r.confidence_notes}</div>` : ''}
          <button class="btn-sm dismiss-btn">${t('analysis.result.dismiss')}</button>
        </div>
      `;
    }

    // queued or running (possibly retrying)
    const isRetrying = this._jobAttemptCount > 1;
    let statusLabel: string;
    if (isRetrying) {
      statusLabel = t('analysis.processing.retry').replace('{n}', String(this._jobAttemptCount));
    } else if (this._jobStatus === 'running') {
      statusLabel = t('analysis.processing.running');
    } else {
      statusLabel = t('analysis.processing.queued');
    }

    return `
      <div class="job-panel job-panel--processing">
        <div class="spinner"></div>
        <div class="job-panel__message">${statusLabel}</div>
        <div class="job-panel__hint">${t('analysis.processing.hint')}</div>
        ${this._jobError ? `<div class="job-panel__error-detail">${this._truncateError(this._jobError)}</div>` : ''}
      </div>
    `;
  }

  private _truncateError(msg: string): string {
    // Extract the core error — drop long stack traces or JSON bodies
    const clean = msg
      .replace(/\{.*?\}/gs, '')   // strip JSON blobs
      .replace(/\s+/g, ' ')
      .trim();
    return clean.length > 120 ? clean.slice(0, 120) + '…' : clean;
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .page { padding: var(--space-6); max-width: 680px; margin: 0 auto; }
        h2 { font-size: var(--font-size-xl); margin-bottom: var(--space-6); }
        h3 { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
          color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.05em;
          margin: var(--space-6) 0 var(--space-3); }

        /* ── Job panel ─────────────────────────────────────────────── */
        .job-panel {
          border-radius: var(--radius-md); padding: var(--space-4);
          margin: var(--space-4) 0; border: 1px solid var(--color-border);
        }
        .job-panel--processing {
          border-color: var(--color-accent); background: var(--color-accent-light, #f0f4ff);
          text-align: center;
        }
        .job-panel--success {
          border-color: var(--color-success);
        }
        .job-panel--error {
          border-color: var(--color-danger); background: var(--color-danger-light, #fff0f0);
          text-align: center;
        }
        .job-panel--warning {
          border-color: var(--color-warning); background: var(--color-warning-light, #fffbf0);
          text-align: center;
        }
        .job-panel__error-detail {
          font-size: var(--font-size-xs); color: var(--color-danger);
          background: rgba(0,0,0,0.04); border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3); margin: var(--space-2) 0;
          text-align: left; word-break: break-word; font-family: monospace;
        }

        /* Spinner */
        @keyframes pi-spin { to { transform: rotate(360deg); } }
        .spinner {
          width: 28px; height: 28px;
          border: 3px solid var(--color-border);
          border-top-color: var(--color-accent);
          border-radius: 50%;
          animation: pi-spin 0.8s linear infinite;
          margin: 0 auto var(--space-3);
        }

        .job-panel__icon { font-size: 24px; color: var(--color-danger); margin-bottom: var(--space-2); }
        .job-panel__message { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); margin-bottom: var(--space-1); }
        .job-panel__hint { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-3); }

        .job-panel__header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
        .job-panel__title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
        .job-panel__summary { font-size: var(--font-size-sm); color: var(--color-text-secondary); white-space: pre-wrap; line-height: 1.5; margin-bottom: var(--space-3); }
        .job-panel__section-label { font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold); color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: var(--space-2); }
        .job-panel__confidence { font-size: var(--font-size-xs); color: var(--color-text-muted); font-style: italic; margin-top: var(--space-2); margin-bottom: var(--space-3); }

        .indicator-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-3); }
        .indicator-chip {
          font-size: var(--font-size-xs); padding: 3px var(--space-2);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          color: var(--color-text-secondary); white-space: nowrap;
        }
        .indicator-chip.signal { font-weight: var(--font-weight-semibold); }

        /* ── Report list ───────────────────────────────────────────── */
        .report { border: 1px solid var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-4); margin-bottom: var(--space-3); }
        .report-header { display: flex; align-items: flex-start; gap: var(--space-3); }
        .signal-badge { padding: 2px var(--space-2); border-radius: var(--radius-sm);
          font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
          color: #fff; white-space: nowrap; }
        .report-meta { flex: 1; min-width: 0; }
        .report-date { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-1); }
        .summary { font-size: var(--font-size-sm); color: var(--color-text-secondary);
          white-space: pre-wrap; margin-top: var(--space-2); line-height: 1.5; }
        .report-actions { display: flex; gap: var(--space-2); margin-top: var(--space-3); }
        .btn-sm { font-size: var(--font-size-xs); padding: var(--space-1) var(--space-3);
          border: 1px solid var(--color-border); border-radius: var(--radius-sm);
          color: var(--color-text-secondary); cursor: pointer; background: transparent; }
        .btn-sm:hover { border-color: var(--color-accent); color: var(--color-accent); }
        .btn-danger { border-color: var(--color-danger); color: var(--color-danger); }
        .btn-danger:hover { background: var(--color-danger); color: #fff; }
        .confirm-bar { font-size: var(--font-size-xs); color: var(--color-danger);
          display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-2); }
        .detail-section { margin-top: var(--space-3); border-top: 1px solid var(--color-border); padding-top: var(--space-3); }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
          gap: var(--space-2); margin-top: var(--space-2); }
        .metric-cell { background: var(--color-bg-secondary); border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3); }
        .metric-label { display: block; font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .metric-val { display: block; font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); margin-top: 2px; }
        .confidence { font-size: var(--font-size-xs); color: var(--color-text-muted);
          margin-top: var(--space-2); font-style: italic; }
        .provider { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .empty { color: var(--color-text-muted); font-size: var(--font-size-sm); padding: var(--space-4) 0; }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-6);
          cursor: pointer; background: transparent; }
      </style>
      <div class="page">
        <h2>${t('analysis.title')}</h2>
        <pi-pdf-uploader id="uploader"></pi-pdf-uploader>

        ${this._renderJobPanel()}

        <h3>${t('analysis.history')}</h3>
        ${this._error ? `<div class="error">${this._error}</div>` : ''}
        ${this._reports.length === 0 && !this._error ? `<div class="empty">${t('analysis.no_reports')}</div>` : ''}
        ${this._reports.map((r) => {
          const isExpanded = this._expandedId === r.id;
          const isConfirming = this._confirmDeleteId === r.id;
          return `
            <div class="report" data-id="${r.id}">
              <div class="report-header">
                ${r.global_signal ? `<span class="signal-badge" style="background:${this._signalColor(r.global_signal)}">${this._signalLabel(r.global_signal)}</span>` : ''}
                <div class="report-meta">
                  ${r.report_date ? `<div class="report-date">${t('analysis.report_date')}: ${r.report_date}</div>` : ''}
                  ${r.executive_summary ? `<div class="summary">${r.executive_summary}</div>` : ''}
                  <div class="provider">${r.provider} · ${r.model_version}</div>
                </div>
              </div>
              ${isExpanded && this._expandedDetail ? `
                <div class="detail-section">
                  <div style="font-size:var(--font-size-xs);font-weight:var(--font-weight-semibold);color:var(--color-text-secondary);margin-bottom:var(--space-1)">${t('analysis.metrics')}</div>
                  ${this._renderMetrics(this._expandedDetail.extracted_metrics)}
                  ${this._expandedDetail.confidence_notes ? `<div class="confidence">${t('analysis.confidence_notes')}: ${this._expandedDetail.confidence_notes}</div>` : ''}
                </div>
              ` : ''}
              <div class="report-actions">
                <button class="btn-sm expand-btn" data-id="${r.id}">${isExpanded ? '▲ ' + t('analysis.hide_metrics') : '▼ ' + t('analysis.show_metrics')}</button>
                ${isConfirming ? `
                  <span class="confirm-bar">
                    ${t('analysis.delete.confirm')}
                    <button class="btn-sm btn-danger confirm-yes-btn" data-id="${r.id}">${t('common.button.confirm')}</button>
                    <button class="btn-sm cancel-btn">${t('common.button.cancel')}</button>
                  </span>
                ` : `<button class="btn-sm btn-danger delete-btn" data-id="${r.id}">${t('analysis.delete')}</button>`}
              </div>
            </div>
          `;
        }).join('')}
        <button class="back-btn" id="back-btn">${t('common.button.back')}</button>
      </div>
    `;
  }

  protected afterRender(): void {
    const uploader = this.shadow.getElementById('uploader') as HTMLElement & { portfolioId: string; holdingId: string };
    if (uploader) {
      uploader.portfolioId = this._portfolioId;
      uploader.holdingId   = this._holdingId;
    }

    this.shadow.getElementById('uploader')?.addEventListener('upload-queued', (e) => {
      const jobId = (e as CustomEvent<{ job_id: string }>).detail?.job_id;
      if (jobId) {
        this._stopPolling();
        this._jobId = jobId;
        this._jobStatus = 'queued';
        this._jobAttemptCount = 0;
        this._jobError = null;
        this._jobResult = null;
        this._rerender();
        this._startPolling();
      }
    });

    this.shadow.querySelector('.dismiss-btn')?.addEventListener('click', () => this._dismissJob());

    this.shadow.getElementById('back-btn')?.addEventListener('click', () =>
      navigate(`/portfolios/${this._portfolioId}/assets/${this._holdingId}`));

    this.shadow.querySelectorAll('.expand-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = (btn as HTMLElement).dataset['id']!;
        void this._toggleExpand(id);
      });
    });

    this.shadow.querySelectorAll('.delete-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmDeleteId = (btn as HTMLElement).dataset['id']!;
        this._rerender();
      });
    });

    this.shadow.querySelectorAll('.cancel-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._confirmDeleteId = null;
        this._rerender();
      });
    });

    this.shadow.querySelectorAll('.confirm-yes-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = (btn as HTMLElement).dataset['id']!;
        void this._delete(id);
      });
    });
  }

  private async _toggleExpand(id: string): Promise<void> {
    if (this._expandedId === id) {
      this._expandedId = null;
      this._expandedDetail = null;
    } else {
      this._expandedId = id;
      this._expandedDetail = null;
      this._rerender();
      try {
        this._expandedDetail = await getReport(id);
      } catch {
        this._expandedDetail = null;
      }
    }
    this._rerender();
  }

  private async _delete(id: string): Promise<void> {
    try {
      await deleteReport(id);
      if (this._expandedId === id) { this._expandedId = null; this._expandedDetail = null; }
      this._confirmDeleteId = null;
      await this._load();
    } catch {
      this._confirmDeleteId = null;
      this._error = t('common.error.generic');
      this._rerender();
    }
  }
}

customElements.define('pi-analysis-screen', AnalysisScreen);
