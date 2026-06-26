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
  cpf?: string;
  role?: string;
  accept_terms: boolean;
  marketing_consent?: boolean;
}): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/register/', payload);
  persistAuth(res.data);
  return res.data;
}

// ── Cadastro diferido (conta só criada quando o usuário entra de fato) ──────────

export interface RegisterStartPayload {
  email: string; full_name: string; phone?: string; cpf: string;
  password: string; password_confirm: string; role?: string;
  accept_terms: boolean; marketing_consent?: boolean;
  plan_slug: string; billing_period?: string; coupon_code?: string;
}

export async function registerStart(payload: RegisterStartPayload): Promise<{ token: string; email_otp_sent: boolean }> {
  const res = await api.post('/api/auth/register/start/', payload);
  return res.data;
}

export async function registerVerifyEmail(token: string, code: string): Promise<{ verified: boolean }> {
  const res = await api.post('/api/auth/register/verify-email/', { token, code });
  return res.data;
}

export async function registerResendEmail(token: string): Promise<{ email_otp_sent: boolean }> {
  const res = await api.post('/api/auth/register/resend-email/', { token });
  return res.data;
}

export async function registerComplete(token: string): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/register/complete/', { token });
  persistAuth(res.data);
  return res.data;
}

export async function registerStatus(token: string): Promise<{ ready: boolean } & Partial<LoginResponse>> {
  const res = await api.post('/api/auth/register/status/', { token });
  if (res.data?.ready && res.data?.access) persistAuth(res.data as LoginResponse);
  return res.data;
}

// ── Handoff de sessão app <-> web ───────────────────────────────────────────
// Retorno automático logado: o site (no Safari) gera um token de uso único e monta um
// universal link; ao abrir o app, a WebView troca o token por uma sessão JWT. Assim o
// usuário que assinou no site entra no app sem digitar a senha de novo.

/** Gera um token de handoff para o usuário autenticado (chamado no site). */
export async function startAppHandoff(): Promise<{ token: string; expires_in: number }> {
  const res = await api.post('/api/auth/app-handoff/', {});
  return res.data;
}

/** Troca o token de handoff por uma sessão JWT (chamado dentro da WebView do app). */
export async function exchangeAppHandoff(token: string): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>('/api/auth/app-handoff/exchange/', { token });
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

// ─── Child / Dependent accounts ─────────────────────────────────────────────

export async function createChildAccount(payload: {
  full_name: string;
  email: string;
  phone?: string;
  password: string;
  password_confirm: string;
}): Promise<import('../types').User> {
  const res = await api.post<import('../types').User>('/api/auth/children/create/', payload);
  return res.data;
}

export async function linkExistingChild(email: string): Promise<
  { id: number; child: number; child_detail: { full_name: string; email: string } } |
  { detail: string; requires_invite: true; invite: import('../types').DependentInvite }
> {
  const res = await api.post('/api/auth/children/link/', { email });
  return res.data;
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
