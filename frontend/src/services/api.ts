import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

function resolveBaseUrl(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL as string) || '';
  if (configured) return configured;
  // Dev fallback only — VITE_API_BASE_URL must be set in production.
  return 'http://localhost:8000';
}

const BASE_URL = resolveBaseUrl();

/** Resolve a media URL — backend now returns absolute URLs via request context. */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http')) return path;
  // Fallback for any relative paths still in localStorage cache
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${BASE_URL}${normalized}`;
}

export const TOKEN_KEY = 'th_access';
export const REFRESH_KEY = 'th_refresh';
export const USER_KEY = 'th_user';

let isRefreshing = false;
let pendingRequests: Array<(token: string) => void> = [];

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

async function refreshToken(): Promise<string> {
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!refresh) throw new Error('no refresh token');
  const res = await axios.post(`${BASE_URL}/api/auth/token/refresh/`, { refresh });
  const newAccess = res.data.access;
  localStorage.setItem(TOKEN_KEY, newAccess);
  if (res.data.refresh) localStorage.setItem(REFRESH_KEY, res.data.refresh);
  return newAccess;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes('/auth/login') &&
      !original.url?.includes('/auth/token/refresh') &&
      !original.url?.includes('/auth/register')
    ) {
      original._retry = true;
      if (isRefreshing) {
        return new Promise((resolve) => {
          pendingRequests.push((token) => {
            if (original.headers) original.headers.Authorization = `Bearer ${token}`;
            resolve(api(original));
          });
        });
      }
      isRefreshing = true;
      try {
        const token = await refreshToken();
        pendingRequests.forEach((cb) => cb(token));
        pendingRequests = [];
        if (original.headers) original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      } catch (err) {
        pendingRequests = [];
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  },
);

export default api;

const FIELD_LABELS: Record<string, string> = {
  email: 'E-mail',
  password: 'Senha',
  password_confirm: 'Confirmação de senha',
  username: 'Usuário',
  first_name: 'Nome',
  last_name: 'Sobrenome',
  full_name: 'Nome completo',
  name: 'Nome',
  phone: 'Celular',
  role: 'Tipo de conta',
  accept_terms: 'Termos de uso',
  display_name: 'Nome de exibição',
  birth_year: 'Ano de nascimento',
  gender: 'Gênero',
  home_state: 'Estado',
  home_city: 'Cidade',
  travel_radius_km: 'Raio de viagem',
  competitive_level: 'Nível competitivo',
  tennis_class: 'Classe',
  category_id: 'Categoria',
  athlete_email: 'E-mail do aluno',
  marketing_consent: 'Comunicações',
  edition: 'Torneio',
  edition_id: 'Torneio',
  category: 'Categoria',
  player: 'Jogador',
  from_date: 'Data inicial',
  to_date: 'Data final',
  entry_close_at: 'Prazo de inscrição',
  non_field_errors: '',
  detail: '',
};

function humanizeKey(key: string): string {
  if (key in FIELD_LABELS) return FIELD_LABELS[key];
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusFallback(status: number | undefined): string | null {
  if (status === 401 || status === 403) return 'Sessão expirada ou acesso não autorizado.';
  if (status === 404) return 'Não encontramos o que você procurava.';
  if (status && status >= 500) return 'O servidor está com instabilidade. Tente novamente em instantes.';
  return null;
}

function validationFallback(status: number | undefined): string {
  if (status === 400 || status === 422) return 'Revise os dados informados e tente novamente.';
  return 'Algo deu errado. Tente novamente em instantes.';
}

function safeApiMessage(value: string): string | null {
  const text = value.trim();
  if (!text || text.length > 240) return null;
  if (/^\s*[{[]/.test(text) || /<[^>]+>/.test(text)) return null;
  if (/\b(traceback|stack trace|exception|integrityerror|validationerror|keyerror|typeerror|valueerror)\b/i.test(text)) return null;
  if (/\b(select|insert|update|delete|where|join)\b.+\b(from|into|set|table)\b/i.test(text)) return null;
  if (/(\/api\/|\.py\b|\.js\b|\.tsx\b|\.ts\b|[a-z]+_[a-z0-9_]+)/i.test(text)) return null;
  return text;
}

function stringifyApiErrorValue(value: unknown): string {
  if (typeof value === 'string') return safeApiMessage(value) ?? '';
  if (Array.isArray(value)) return value.map(stringifyApiErrorValue).filter(Boolean).join(', ');
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, child]) => {
        const label = humanizeKey(key);
        const text = stringifyApiErrorValue(child);
        if (!text) return '';
        return label ? `${label}: ${text}` : text;
      })
      .filter(Boolean)
      .join(', ');
  }
  return '';
}

export function extractApiError(err: unknown): string {
  const ax = err as AxiosError<Record<string, unknown>>;
  const status = ax.response?.status;
  const data = ax.response?.data;

  if (!data) {
    if (ax.request && !ax.response) return 'Não foi possível conectar ao servidor. Verifique sua conexão.';
    return 'Algo deu errado. Tente novamente em instantes.';
  }

  const fallback = statusFallback(status);
  if (fallback) return fallback;

  if (typeof data === 'object') {
    const detail = (data as Record<string, unknown>).detail;
    if (typeof detail === 'string') {
      const safeDetail = safeApiMessage(detail);
      if (safeDetail) return safeDetail;
    }
    const parts: string[] = [];
    for (const [k, v] of Object.entries(data)) {
      const label = humanizeKey(k);
      const value = stringifyApiErrorValue(v);
      if (!value) continue;
      parts.push(label ? `${label}: ${value}` : value);
    }
    if (parts.length) return parts.join(' • ');
  }

  return validationFallback(status);
}
