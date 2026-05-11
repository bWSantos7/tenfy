import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';

export const TOKEN_KEY   = 'th_access';
export const REFRESH_KEY = 'th_refresh';
export const USER_KEY    = 'th_user';

// SecureStore wrappers — uses Keychain (iOS) / EncryptedSharedPreferences (Android)
// Falls back silently on web where SecureStore is unavailable.
async function secureGet(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function secureSet(key: string, value: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(key, value);
  } catch {
    // no-op on unsupported platforms
  }
}

async function secureDelete(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key);
  } catch {
    // no-op
  }
}

export const storage = {
  get: secureGet,
  set: secureSet,
  delete: secureDelete,
  deleteMultiple: (keys: string[]) => Promise.all(keys.map(secureDelete)),
};


function resolveBaseUrl(): string {
  const configured = (
    process.env.EXPO_PUBLIC_API_BASE_URL
    || process.env.EXPO_PUBLIC_API_URL
    || ''
  ).trim();
  if (configured) return configured;
  return 'https://api.tennis.app.br';
}

export const BASE_URL = resolveBaseUrl();

export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http')) return path;
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${BASE_URL}${normalized}`;
}

let isRefreshing = false;
let pendingRequests: Array<(token: string) => void> = [];

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

const PUBLIC_PATHS = ['/api/auth/login/', '/api/auth/register/', '/api/auth/password-reset/', '/api/auth/token/refresh/'];

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const isPublic = PUBLIC_PATHS.some((p) => config.url?.includes(p));
  if (!isPublic) {
    const token = await secureGet(TOKEN_KEY);
    if (token && config.headers) config.headers.Authorization = `Bearer ${token}`;
  } else if (config.headers) {
    delete config.headers.Authorization;
  }
  return config;
});

async function refreshToken() {
  const refresh = await secureGet(REFRESH_KEY);
  if (!refresh) throw new Error('no refresh token');
  const res = await axios.post(`${BASE_URL}/api/auth/token/refresh/`, { refresh });
  const newAccess = res.data.access;
  await secureSet(TOKEN_KEY, newAccess);
  if (res.data.refresh) await secureSet(REFRESH_KEY, res.data.refresh);
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
        await storage.deleteMultiple([TOKEN_KEY, REFRESH_KEY, USER_KEY]);
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  },
);

export default api;

// Friendly labels for backend field names — keeps user-facing toasts clean
// instead of leaking raw API keys (e.g. `entry_close_at: ...`).
const FIELD_LABELS: Record<string, string> = {
  email: 'E-mail',
  password: 'Senha',
  password_confirm: 'Confirmação de senha',
  full_name: 'Nome completo',
  phone: 'Celular',
  role: 'Tipo de conta',
  accept_terms: 'Termos de uso',
  marketing_consent: 'Comunicações',
  display_name: 'Nome de exibição',
  birth_year: 'Ano de nascimento',
  gender: 'Gênero',
  home_state: 'Estado',
  home_city: 'Cidade',
  travel_radius_km: 'Raio de viagem',
  travel_states: 'Estados de viagem',
  competitive_level: 'Nível competitivo',
  tennis_class: 'Classe',
  category_id: 'Categoria',
  edition: 'Torneio',
  edition_id: 'Torneio',
  category: 'Categoria',
  player: 'Jogador',
  from_date: 'Data inicial',
  to_date: 'Data final',
  entry_close_at: 'Prazo de inscrição',
  is_youth: 'Categoria juvenil',
  slug: 'Identificador',
  confidence: 'Confiabilidade',
  near_profile: 'Perto do perfil',
  source_url: 'Link da fonte',
  ranking_source_url: 'Link do ranking',
  candidate_entry_links: 'Links de inscritos',
  organization_slug: 'Entidade',
  synced_at: 'Última atualização',
  athlete_email: 'E-mail do aluno',
  home_lat: 'Latitude da cidade',
  home_lng: 'Longitude da cidade',
  non_field_errors: '',
  detail: '',
};

function humanizeFieldKey(key: string): string {
  if (key in FIELD_LABELS) return FIELD_LABELS[key];
  // Fallback: turn snake_case into Title Case for unknown keys.
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusFallback(status: number | undefined): string | null {
  if (status === 401 || status === 403) return 'Sua sessão expirou ou você não tem acesso a este recurso.';
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
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(stringifyApiErrorValue).filter(Boolean).join(', ');
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, child]) => {
        const label = humanizeFieldKey(key);
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
  const data = ax.response?.data;
  const status = ax.response?.status;
  if (!data) {
    if (ax.request && !ax.response) {
      return 'Não foi possível conectar ao servidor. Verifique sua conexão com a internet.';
    }
    return 'Algo deu errado. Tente novamente em instantes.';
  }
  const fallback = statusFallback(status);
  if (fallback) return fallback;
  if (typeof data === 'string') return safeApiMessage(data) ?? validationFallback(status);
  const detail = (data as Record<string, unknown>).detail;
  if (typeof detail === 'string') {
    const safeDetail = safeApiMessage(detail);
    if (safeDetail) return safeDetail;
  }
  const parts: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    const label = humanizeFieldKey(k);
    const value = stringifyApiErrorValue(v);
    if (!value) continue;
    parts.push(label ? `${label}: ${value}` : value);
  }
  if (parts.length) return parts.join(' • ');
  return validationFallback(status);
}
