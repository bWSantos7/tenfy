import api, { REFRESH_KEY, TOKEN_KEY, USER_KEY } from './api';
import { LoginResponse, User } from '../types';

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/login/', { email, password });
  persistAuth(res.data);
  return res.data;
}

export async function register(payload: {
  email: string;
  phone: string;
  password: string;
  password_confirm: string;
  full_name?: string;
  role?: string;
  accept_terms: boolean;
  marketing_consent?: boolean;
}): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/register/', payload);
  persistAuth(res.data);
  return res.data;
}

export async function fetchMe(): Promise<User> {
  const res = await api.get<User>('/api/auth/me/');
  localStorage.setItem(USER_KEY, JSON.stringify(res.data));
  return res.data;
}

export async function updateMe(patch: Partial<User>): Promise<User> {
  const res = await api.patch<User>('/api/auth/me/', patch);
  localStorage.setItem(USER_KEY, JSON.stringify(res.data));
  return res.data;
}

export async function logout(): Promise<void> {
  const refresh = localStorage.getItem(REFRESH_KEY);
  try {
    if (refresh) await api.post('/api/auth/logout/', { refresh });
  } catch {
    // ignore
  } finally {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  }
}

export async function changePassword(old_password: string, new_password: string) {
  return api.post('/api/auth/change-password/', {
    old_password,
    new_password,
    new_password_confirm: new_password,
  });
}

export async function deleteAccount() {
  await api.delete('/api/auth/delete-account/');
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

// ─── OTP ────────────────────────────────────────────────────────────────────

export async function sendEmailOtp(): Promise<void> {
  await api.post('/api/auth/send-email-otp/');
}

export async function verifyEmailOtp(code: string): Promise<void> {
  await api.post('/api/auth/verify-email/', { code });
}

export async function uploadAvatar(file: File): Promise<import('../types').User> {
  const form = new FormData();
  form.append('avatar', file);
  const res = await api.post<import('../types').User>('/api/auth/me/avatar/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  localStorage.setItem(USER_KEY, JSON.stringify(res.data));
  return res.data;
}

function persistAuth(data: LoginResponse) {
  localStorage.setItem(TOKEN_KEY, data.access);
  localStorage.setItem(REFRESH_KEY, data.refresh);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export function loadStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}
