import { get, post } from './client.js';
import type { AiReport, Notification } from './types.js';

export const uploadPdf       = (holdingId: string, file: File) => {
  const form = new FormData();
  form.append('file', file);
  // Use raw fetch — client.ts wraps JSON; PDF upload is multipart.
  return fetch(
    `${import.meta.env.VITE_BACKEND_BASE_URL ?? 'http://localhost:8000'}/holdings/${holdingId}/analyses`,
    { method: 'POST', body: form, credentials: 'include' },
  ).then((r) => r.json() as Promise<AiReport>);
};

export const getReport       = (holdingId: string, reportId: string) =>
  get<AiReport>(`/holdings/${holdingId}/analyses/${reportId}`);

export const listReports     = (holdingId: string) =>
  get<AiReport[]>(`/holdings/${holdingId}/analyses`);

export const getNotifications = () =>
  get<Notification[]>('/me/notifications');

export const dismissNotification = (reportId: string) =>
  post<void>(`/me/notifications/${reportId}/dismiss`);
