import { get, post, del } from './client.js';
import type { AdminUserDetail, AdminUserListResponse, AdminRoleOut, ResetPasswordResponse } from './types.js';

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
