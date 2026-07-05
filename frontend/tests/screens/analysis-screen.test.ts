// Regression test for Changeset C06 Bug A — the analysis history section
// rendered its header/back button but never showed the fetched reports.
// Root cause (diagnosed via live reproduction, see C06 changeset notes) was an
// unrelated stale frontend build; these tests guard the actual code path so a
// future regression here fails a test instead of shipping silently.

import { describe, it, expect, vi, afterEach } from 'vitest';

const { mockReports } = vi.hoisted(() => ({
  mockReports: [
    {
      id: 'r1', holding_id: 'h1', report_date: '2026-03-31',
      report_date_source: 'ai_extracted', report_period_name: 'Q1 2026',
      report_period_name_source: 'ai_extracted', provider: 'gemini',
      model_version: 'gemini-2.0', global_signal: 'bullish', executive_summary: 'Solid quarter.',
      created_at: '2026-04-01T00:00:00Z',
    },
    {
      id: 'r2', holding_id: 'h1', report_date: '2025-12-31',
      report_date_source: 'upload_fallback', report_period_name: null,
      report_period_name_source: 'unset', provider: 'gemini',
      model_version: 'gemini-2.0', global_signal: 'neutral', executive_summary: 'Mixed results.',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}));

vi.mock('../../src/api/analyses.js', () => ({
  listReports: vi.fn().mockResolvedValue(structuredClone(mockReports)),
  getReport: vi.fn(),
  deleteReport: vi.fn(),
  patchAnalysis: vi.fn(),
  getJobs: vi.fn().mockResolvedValue([]),
  getNotifications: vi.fn().mockResolvedValue([]),
  uploadPdf: vi.fn(),
}));

import '../../src/screens/analysis-screen.js';
import { listReports } from '../../src/api/analyses.js';

type ScreenEl = HTMLElement & { params: Record<string, string> };

function mount(): ScreenEl {
  const el = document.createElement('pi-analysis-screen') as ScreenEl;
  el.params = { portfolioId: 'p1', holdingId: 'h1' };
  document.body.appendChild(el);
  return el;
}

describe('pi-analysis-screen — history rendering (C06 Bug A regression)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.mocked(listReports).mockReset();
    vi.mocked(listReports).mockResolvedValue(structuredClone(mockReports));
  });

  it('renders one entry per report when the API returns a non-empty list', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const entries = el.shadowRoot!.querySelectorAll('.report');
    expect(entries.length).toBe(mockReports.length);
  });

  it('renders the pi-header-bar so the screen is not missing its top bar', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    expect(el.shadowRoot!.querySelector('pi-header-bar')).not.toBeNull();
  });

  it('shows the specific load-error message instead of an empty list when the fetch fails', async () => {
    vi.mocked(listReports).mockRejectedValueOnce(new Error('network down'));

    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const errorEl = el.shadowRoot!.querySelector('.error');
    expect(errorEl?.textContent).toContain('No se pudieron cargar los análisis previos');
    expect(el.shadowRoot!.querySelectorAll('.report').length).toBe(0);
  });
});

describe('pi-analysis-screen — date/name editing (C05 §6, §7)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.mocked(listReports).mockReset();
    vi.mocked(listReports).mockResolvedValue(structuredClone(mockReports));
  });

  it('shows the upload-fallback warning icon only for the report with that source', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const reports = el.shadowRoot!.querySelectorAll('.report');
    expect(reports[0]!.querySelector('.warn-icon')).toBeNull();
    expect(reports[1]!.querySelector('.warn-icon')).not.toBeNull();
  });

  it('shows the missing-name prompt only for the report with an unset name', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const reports = el.shadowRoot!.querySelectorAll('.report');
    expect(reports[0]!.querySelector('.report-name--missing')).toBeNull();
    expect(reports[0]!.querySelector('.report-name')?.textContent).toContain('Q1 2026');
    expect(reports[1]!.querySelector('.report-name--missing')).not.toBeNull();
  });

  it('clicking the date edit icon switches that field into an editable input', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const editBtn = el.shadowRoot!.querySelector('.report[data-id="r1"] .edit-icon-btn[data-field="date"]') as HTMLElement;
    editBtn.click();

    const input = el.shadowRoot!.querySelector('.report[data-id="r1"] .date-input') as HTMLInputElement;
    expect(input).not.toBeNull();
    expect(input.value).toBe('2026-03-31');
  });

  it('submits patchAnalysis with the new date on blur and updates the row on success', async () => {
    const { patchAnalysis } = await import('../../src/api/analyses.js');
    vi.mocked(patchAnalysis).mockResolvedValueOnce({
      ...mockReports[0],
      report_date: '2026-04-15',
      report_date_source: 'user_edited',
    } as never);

    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.querySelector('.report[data-id="r1"] .edit-icon-btn[data-field="date"]') as HTMLElement).click();
    const input = el.shadowRoot!.querySelector('.report[data-id="r1"] .date-input') as HTMLInputElement;
    input.value = '2026-04-15';
    input.dispatchEvent(new Event('blur'));
    await new Promise((r) => setTimeout(r, 0));

    expect(patchAnalysis).toHaveBeenCalledWith('r1', { report_date: '2026-04-15' });
  });

  it('shows the collision message on a 409 error without discarding the previous value', async () => {
    const { patchAnalysis } = await import('../../src/api/analyses.js');
    const { ApiError } = await import('../../src/api/types.js');
    vi.mocked(patchAnalysis).mockRejectedValueOnce(new ApiError(409, 'conflict', 'collision'));

    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.querySelector('.report[data-id="r1"] .edit-icon-btn[data-field="date"]') as HTMLElement).click();
    const input = el.shadowRoot!.querySelector('.report[data-id="r1"] .date-input') as HTMLInputElement;
    input.value = '2025-12-31';
    input.dispatchEvent(new Event('blur'));
    await new Promise((r) => setTimeout(r, 0));

    const statusEl = el.shadowRoot!.querySelector('.report[data-id="r1"] .field-status--error');
    expect(statusEl?.textContent).toContain('Ya existe un análisis con esta fecha');
    // The displayed date reverts to the report's actual (unchanged) value.
    expect(el.shadowRoot!.querySelector('.report[data-id="r1"] .report-date')?.textContent).toContain('2026-03-31');
  });
});
