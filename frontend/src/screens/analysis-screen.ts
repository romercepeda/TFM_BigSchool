import { BaseComponent } from '../components/common/base-component.js';
import '../components/header-bar.js';
import '../components/pdf-uploader.js';
import { t } from '../i18n/i18n.js';
import { listReports, getReport, deleteReport, patchAnalysis, getJobs } from '../api/analyses.js';
import { navigate } from '../router/router.js';
import type { RouteParams } from '../router/router.js';
import { ApiError } from '../api/types.js';
import type { AiReportSummary, AiReportDetail } from '../api/types.js';
import { formatDate } from '../utils/format.js';

type EditField = 'date' | 'name';
type FieldStatus = 'saving' | 'saved' | 'error';

export class AnalysisScreen extends BaseComponent {
  private _portfolioId = '';
  private _holdingId = '';
  private _reports: AiReportSummary[] = [];
  private _expandedId: string | null = null;
  private _expandedDetail: AiReportDetail | null = null;
  private _confirmDeleteId: string | null = null;
  private _error = '';

  // Inline date/name editing (Changeset C05 §7)
  private _editing: { id: string; field: EditField } | null = null;
  private _fieldStatus: Record<string, FieldStatus> = {};
  private _fieldError: Record<string, string> = {};

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
    } catch (ex) {
      console.error('Failed to load analysis history', ex);
      this._error = t('analysis.history.load_error');
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
          background: color-mix(in srgb, currentColor 8%, transparent); border-radius: var(--radius-sm);
          padding: var(--space-2) var(--space-3); margin: var(--space-2) 0;
          text-align: left; word-break: break-word; font-family: var(--font-family-mono);
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
          font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
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
        .report-date, .report-name { font-size: var(--font-size-xs); color: var(--color-text-muted);
          margin-bottom: var(--space-1); display: flex; align-items: center; gap: var(--space-1); }
        .report-name { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .report-processed { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-1); }
        .report-name--missing { color: var(--color-warning); font-style: italic; }
        .warn-icon { color: var(--color-warning); cursor: help; font-size: var(--font-size-xs); }
        .edit-icon-btn { border: none; background: transparent; color: var(--color-text-muted);
          cursor: pointer; font-size: var(--font-size-xs); padding: 0 2px; opacity: 0.6; }
        .edit-icon-btn:hover { opacity: 1; color: var(--color-accent); }
        .edit-row { margin-bottom: var(--space-1); }
        .edit-input { font-size: var(--font-size-xs); padding: 2px var(--space-2);
          border: 1px solid var(--color-accent); border-radius: var(--radius-sm); }
        .field-status { font-size: 10px; margin-left: var(--space-1); }
        .field-status--saving { color: var(--color-text-muted); }
        .field-status--saved { color: var(--color-success); }
        .field-status--error { color: var(--color-danger); }
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
        .metric-val {
          display: block; font-family: var(--font-family-mono); font-variant-numeric: tabular-nums;
          font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); margin-top: 2px;
        }
        .confidence { font-size: var(--font-size-xs); color: var(--color-text-muted);
          margin-top: var(--space-2); font-style: italic; }
        .provider { font-size: var(--font-size-xs); color: var(--color-text-muted); }
        .shared-label { font-style: italic; }
        .empty { color: var(--color-text-muted); font-size: var(--font-size-sm); padding: var(--space-4) 0; }
        .error { color: var(--color-danger); font-size: var(--font-size-sm); }
        .back-btn { border: 1px solid var(--color-border); padding: var(--space-2) var(--space-4);
          border-radius: var(--radius-sm); color: var(--color-text-secondary); margin-top: var(--space-6);
          cursor: pointer; background: transparent; }
      </style>
      <pi-header-bar></pi-header-bar>
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
                  ${this._renderDateField(r)}
                  <div class="report-processed">${t('analysis.processed_date')}: ${formatDate(r.created_at, { dateStyle: 'medium' })}</div>
                  ${this._renderNameField(r)}
                  ${r.executive_summary ? `<div class="summary">${r.executive_summary}</div>` : ''}
                  <div class="provider">${r.provider} · ${r.model_version}${!r.is_own ? ` · <span class="shared-label">${t('analysis.history.entry.shared_label')}</span>` : ''}</div>
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
                ${!r.is_own ? '' : isConfirming ? `
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
      navigate(`/app/portfolios/${this._portfolioId}/assets/${this._holdingId}`));

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

    this._wireEditableFields();
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

  // ── Inline date/name editing (Changeset C05 §7) ──────────────────────────────

  private _fieldKey(id: string, field: EditField): string {
    return `${id}:${field}`;
  }

  private _startEdit(id: string, field: EditField): void {
    this._editing = { id, field };
    delete this._fieldStatus[this._fieldKey(id, field)];
    delete this._fieldError[this._fieldKey(id, field)];
    this._rerender();
  }

  private _cancelEdit(): void {
    this._editing = null;
    this._rerender();
  }

  private async _commitEdit(id: string, field: EditField, rawValue: string): Promise<void> {
    const report = this._reports.find((r) => r.id === id);
    if (!report) {
      this._editing = null;
      this._rerender();
      return;
    }

    let value = rawValue;
    if (field === 'date') {
      if (!value || value === report.report_date) {
        this._editing = null;
        this._rerender();
        return;
      }
    } else {
      value = value.trim().slice(0, 40);
      if (value === (report.report_period_name ?? '')) {
        this._editing = null;
        this._rerender();
        return;
      }
    }

    const key = this._fieldKey(id, field);
    this._editing = null;
    this._fieldStatus[key] = 'saving';
    delete this._fieldError[key];
    this._rerender();

    try {
      const body = field === 'date' ? { report_date: value } : { report_period_name: value };
      const updated = await patchAnalysis(id, body);
      const idx = this._reports.findIndex((r) => r.id === id);
      if (idx !== -1) this._reports[idx] = { ...this._reports[idx], ...updated };
      this._fieldStatus[key] = 'saved';
    } catch (ex) {
      this._fieldStatus[key] = 'error';
      this._fieldError[key] = ex instanceof ApiError && ex.status === 409
        ? t('analysis.history.entry.date_collision_error')
        : t('common.save_error');
    }
    this._rerender();
  }

  private _renderDateField(r: AiReportSummary): string {
    const key = this._fieldKey(r.id, 'date');
    const status = this._fieldStatus[key];
    const isEditing = this._editing?.id === r.id && this._editing.field === 'date';
    const showFallbackWarning = r.report_date_source === 'upload_fallback';

    if (isEditing) {
      return `
        <div class="edit-row">
          <input type="date" class="edit-input date-input" data-id="${r.id}" value="${r.report_date ?? ''}" />
        </div>
      `;
    }

    return `
      <div class="report-date">
        ${showFallbackWarning
          ? `<span class="warn-icon" title="${t('analysis.history.entry.date_fallback_warning')}">⚠</span>`
          : ''}
        <span>${t('analysis.report_date')}: ${r.report_date ?? '—'}</span>
        ${r.is_own ? `<button class="edit-icon-btn" data-id="${r.id}" data-field="date" title="${t('common.button.edit')}">✎</button>` : ''}
        ${this._renderFieldStatus(status, this._fieldError[key])}
      </div>
    `;
  }

  private _renderNameField(r: AiReportSummary): string {
    const key = this._fieldKey(r.id, 'name');
    const status = this._fieldStatus[key];
    const isEditing = this._editing?.id === r.id && this._editing.field === 'name';
    const isUnset = r.report_period_name_source === 'unset';

    if (isEditing) {
      return `
        <div class="edit-row">
          <input type="text" maxlength="40" class="edit-input name-input" data-id="${r.id}" value="${r.report_period_name ?? ''}" />
        </div>
      `;
    }

    return `
      <div class="report-name${isUnset ? ' report-name--missing' : ''}">
        <span>${r.report_period_name ?? t('analysis.history.entry.name_missing_warning')}</span>
        ${r.is_own ? `<button class="edit-icon-btn" data-id="${r.id}" data-field="name" title="${t('common.button.edit')}">✎</button>` : ''}
        ${this._renderFieldStatus(status, this._fieldError[key])}
      </div>
    `;
  }

  private _renderFieldStatus(status: FieldStatus | undefined, error?: string): string {
    if (status === 'saving') return `<span class="field-status field-status--saving">${t('common.saving')}</span>`;
    if (status === 'saved') return `<span class="field-status field-status--saved">${t('common.saved')}</span>`;
    if (status === 'error') return `<span class="field-status field-status--error">${error ?? t('common.save_error')}</span>`;
    return '';
  }

  private _wireEditableFields(): void {
    this.shadow.querySelectorAll('.edit-icon-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const el = btn as HTMLElement;
        const id = el.dataset['id']!;
        const field = el.dataset['field'] as EditField;
        this._startEdit(id, field);
      });
    });

    this.shadow.querySelectorAll<HTMLInputElement>('.date-input').forEach((input) => {
      const id = input.dataset['id']!;
      input.addEventListener('blur', () => void this._commitEdit(id, 'date', input.value));
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') input.blur();
        if (e.key === 'Escape') this._cancelEdit();
      });
      input.focus();
    });

    this.shadow.querySelectorAll<HTMLInputElement>('.name-input').forEach((input) => {
      const id = input.dataset['id']!;
      input.addEventListener('blur', () => void this._commitEdit(id, 'name', input.value));
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') input.blur();
        if (e.key === 'Escape') this._cancelEdit();
      });
      input.focus();
    });
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
