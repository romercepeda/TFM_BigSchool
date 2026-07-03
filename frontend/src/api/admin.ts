import { get, post, del } from './client.js';
import type {
  AdminUserDetail, AdminUserListResponse, AdminRoleOut, ResetPasswordResponse,
  CascadeFailureListResponse,
} from './types.js';

export const listAdminUsers = (limit: number, offset: number) =>
  get<AdminUserListResponse>(`/admin/users?limit=${limit}&offset=${offset}`);

export const getAdminUserDetail = (userId: string) =>
  get<AdminUserDetail>(`/admin/users/${userId}`);

export const grantRole = (userId: string, roleCode: string) =>
  post<AdminUserDetail>(`/admin/users/${userId}/roles`, { role_code: roleCode });

export const revokeRole = (userId: string, roleCode: string) =>
  del<AdminUserDetail>(`/admin/users/${userId}/roles/${roleCode}`);

export const resetUserPassword = (userId: string) =>
  post<ResetPasswordResponse>(`/admin/users/${userId}/reset-password`);

export const listAdminRoles = () => get<AdminRoleOut[]>('/admin/roles');

export interface CascadeFailureFilters {
  page?: number;
  pageSize?: number;
  fromDate?: string;
  toDate?: string;
  provider?: string;
  reason?: string;
}

export const listCascadeFailureReports = (filters: CascadeFailureFilters = {}) => {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.fromDate) params.set('from_date', filters.fromDate);
  if (filters.toDate) params.set('to_date', filters.toDate);
  if (filters.provider) params.set('provider', filters.provider);
  if (filters.reason) params.set('reason', filters.reason);
  return get<CascadeFailureListResponse>(`/admin/cascade-failure-reports?${params.toString()}`);
};
