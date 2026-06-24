import { get, post, patch } from './client.js';
import type { LoginResponse, UserResponse } from './types.js';

export interface LoginBody { email: string; password: string; }
export interface RegisterBody { email: string; password: string; }
export interface GuestBody { email: string; }

export const login     = (body: LoginBody)    => post<LoginResponse>('/auth/login',    body);
export const register  = (body: RegisterBody) => post<LoginResponse>('/auth/register', body);
export const guestLogin = (body: GuestBody)   => post<LoginResponse>('/auth/guest',    body);
export const logout    = ()                   => post<void>('/auth/logout');
export const getMe     = ()                   => get<UserResponse>('/auth/me');
export const updateLanguage = (language: string) =>
  patch<{ preferred_language: string }>('/auth/me/language', { language });
