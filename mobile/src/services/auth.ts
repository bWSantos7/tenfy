import api, { REFRESH_KEY, TOKEN_KEY, USER_KEY, storage } from './api';
import { LoginResponse, ParentChild, User } from '../types';

async function persistAuth(data: LoginResponse) {
  await storage.set(TOKEN_KEY, data.access);
  await storage.set(REFRESH_KEY, data.refresh);
  await storage.set(USER_KEY, JSON.stringify(data.user));
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/login/', { email, password });
  await persistAuth(res.data);
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
  await persistAuth(res.data);
  return res.data;
}

export async function fetchMe(): Promise<User> {
  const res = await api.get<User>('/api/auth/me/');
  await storage.set(USER_KEY, JSON.stringify(res.data));
  return res.data;
}

export async function logout() {
  const refresh = await storage.get(REFRESH_KEY);
  try {
    if (refresh) await api.post('/api/auth/logout/', { refresh });
  } catch {
  } finally {
    await storage.deleteMultiple([TOKEN_KEY, REFRESH_KEY, USER_KEY]);
  }
}

export async function deleteAccount() {
  try {
    await api.delete('/api/auth/delete-account/');
  } catch (err: any) {
    const status: number | undefined = err?.response?.status;
    // Network error (no response), 401, or 404 → account is gone or unreachable.
    // Clear tokens so user is logged out instead of stuck with a deleted account.
    if (!status || status === 401 || status === 404) {
      await storage.deleteMultiple([TOKEN_KEY, REFRESH_KEY, USER_KEY]);
      return;
    }
    // Real server rejection (400, 422, 5xx) → account may still exist, let UI show error.
    throw err;
  }
  await storage.deleteMultiple([TOKEN_KEY, REFRESH_KEY, USER_KEY]);
}

export async function sendEmailOtp() { await api.post('/api/auth/send-email-otp/'); }
export async function verifyEmailOtp(code: string) { await api.post('/api/auth/verify-email/', { code }); }

export async function createChildAccount(payload: {
  full_name: string;
  email: string;
  phone?: string;
  password: string;
  password_confirm: string;
}): Promise<ParentChild> {
  const res = await api.post<ParentChild>('/api/auth/children/', payload);
  return res.data;
}

export async function uploadAvatar(asset: { uri: string; fileName?: string | null; mimeType?: string | null; }): Promise<User> {
  const form = new FormData();
  form.append('avatar', { uri: asset.uri, name: asset.fileName || 'avatar.jpg', type: asset.mimeType || 'image/jpeg' } as any);
  const res = await api.post<User>('/api/auth/me/avatar/', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  await storage.set(USER_KEY, JSON.stringify(res.data));
  return res.data;
}

export async function loadStoredUser(): Promise<User | null> {
  const raw = await storage.get(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw) as User; } catch { return null; }
}
