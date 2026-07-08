import { get, patch, del } from './client.js';
import type { AiReportSummary, AiReportDetail, Notification, UploadReportResponse } from './types.js';
import { getCsrfToken } from '../state/auth-state.js';

const BASE_URL: string = import.meta.env.VITE_BACKEND_BASE_URL ?? 'http://localhost:8000';

export const uploadPdf = (portfolioId: string, holdingId: string, file: File): Promise<UploadReportResponse> => {
  const form = new FormData();
  form.append('file', file);
  const headers: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) headers['X-CSRF-Token'] = csrf;
  return fetch(
    `${BASE_URL}/portfolios/${portfolioId}/holdings/${holdingId}/ai-reports`,
    { method: 'POST', body: form, credentials: 'include', headers },
  ).then(async (r) => {
    if (!r.ok) {
      const text = await r.text();
      throw new Error(text || `HTTP ${r.status}`);
    }
    return r.json();
  });
};

export const listReports = (portfolioId: string, holdingId: string) =>
  get<AiReportSummary[]>(`/portfolios/${portfolioId}/holdings/${holdingId}/ai-reports`);

export const getReport = (reportId: string) =>
  get<AiReportDetail>(`/ai-reports/${reportId}`);

export const deleteReport = (reportId: string) =>
  del<void>(`/ai-reports/${reportId}`);

export const patchAnalysis = (
  reportId: string,
  body: { report_date?: string; report_period_name?: string },
) => patch<AiReportDetail>(`/ai-reports/${reportId}`, body);

export const getNotifications = () =>
  get<Notification[]>('/ai-reports/jobs?status_filter=queued,running');

export const getJobs = () =>
  get<Notification[]>('/ai-reports/jobs');
