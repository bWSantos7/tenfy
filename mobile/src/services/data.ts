import api from './api';
import { Alert, CoachAthlete, DependentInvite, Paginated, ParentChild, PlayerCategory, PlayerProfile, PlayerSearchResult, TiData, UtrCandidate, UtrSearchResult, WatchlistItem } from '../types';

// ----- Players -----
// Cache compartilhado de perfis. listProfiles() é chamado por várias telas
// (Home, Perfil, Resultados, Torneios, Detalhe...) conforme o usuário navega.
//
// Duas camadas, ambas seguras:
//   1. In-flight dedup — mescla GETs idênticos simultâneos numa única requisição.
//   2. Cache de TTL curto — serve os mesmos perfis em navegações rápidas sem
//      refazer a requisição. Invalidado em toda mutação de perfil, então nunca
//      esconde uma alteração que o usuário acabou de fazer.
//
// Passe { force: true } para ignorar o cache quando dados frescos são obrigatórios.
const PROFILES_TTL_MS = 30_000;
let _profilesInFlight: Promise<PlayerProfile[]> | null = null;
let _profilesCache: { data: PlayerProfile[]; at: number } | null = null;

/** Descarta o cache de perfis para que o próximo listProfiles() busque de novo. */
export function invalidateProfilesCache() {
  _profilesCache = null;
}

export async function listProfiles(opts?: { force?: boolean }): Promise<PlayerProfile[]> {
  const force = opts?.force === true;
  if (!force && _profilesCache && Date.now() - _profilesCache.at < PROFILES_TTL_MS) {
    return _profilesCache.data;
  }
  if (!force && _profilesInFlight) return _profilesInFlight;
  const pending = (async () => {
    const res = await api.get<Paginated<PlayerProfile> | PlayerProfile[]>('/api/players/profiles/');
    const d = res.data as Paginated<PlayerProfile>;
    return d.results ?? (res.data as PlayerProfile[]);
  })();
  if (!force) _profilesInFlight = pending;
  try {
    const data = await pending;
    _profilesCache = { data, at: Date.now() };
    return data;
  } finally {
    if (!force) _profilesInFlight = null;
  }
}
export async function getProfile(id: number) {
  const res = await api.get<PlayerProfile>(`/api/players/profiles/${id}/`);
  return res.data;
}
export async function createProfile(data: Partial<PlayerProfile>) {
  const res = await api.post<PlayerProfile>('/api/players/profiles/', data);
  invalidateProfilesCache();
  return res.data;
}
export async function updateProfile(id: number, data: Partial<PlayerProfile>) {
  const res = await api.patch<PlayerProfile>(`/api/players/profiles/${id}/`, data);
  invalidateProfilesCache();
  return res.data;
}
export async function deleteProfile(id: number) {
  const res = await api.delete(`/api/players/profiles/${id}/`);
  invalidateProfilesCache();
  return res;
}
export async function setPrimary(id: number) {
  const res = await api.post(`/api/players/profiles/${id}/set_primary/`);
  invalidateProfilesCache();
  return res;
}
export async function listCategories(taxonomy?: string) {
  const url = taxonomy
    ? `/api/players/categories/?taxonomy=${encodeURIComponent(taxonomy)}&page_size=200`
    : '/api/players/categories/?page_size=200';
  const res = await api.get<Paginated<PlayerCategory> | PlayerCategory[]>(url);
  const d = res.data as Paginated<PlayerCategory>;
  return d.results ?? (res.data as PlayerCategory[]);
}

// ----- Watchlist -----
export async function listWatchlist() {
  const res = await api.get<Paginated<WatchlistItem> | WatchlistItem[]>('/api/watchlist/');
  const d = res.data as Paginated<WatchlistItem>;
  return d.results ?? (res.data as WatchlistItem[]);
}
export async function toggleWatchlist(editionId: number, profileId?: number) {
  const res = await api.post<{ watching: boolean; edition_id: number; item?: WatchlistItem }>(
    '/api/watchlist/toggle/',
    { edition_id: editionId, profile_id: profileId ?? null },
  );
  return res.data;
}
export async function deleteWatch(id: number) {
  return api.delete(`/api/watchlist/${id}/`);
}
export const removeWatchlist = deleteWatch;
export async function updateWatch(id: number, patch: Partial<WatchlistItem>) {
  const res = await api.patch<WatchlistItem>(`/api/watchlist/${id}/`, patch);
  return res.data;
}
export async function watchlistSummary() {
  const res = await api.get<{
    total: number;
    active_registrations: number;
    upcoming: number;
    past: number;
    by_status: Record<string, number>;
  }>('/api/watchlist/summary/');
  return res.data;
}

export async function saveResult(watchlistItemId: number, data: {
  category_played?: string;
  position?: number | null;
  wins?: number;
  losses?: number;
  notes?: string;
}) {
  const res = await api.post(`/api/watchlist/${watchlistItemId}/result/`, data);
  return res.data;
}

// ----- Coach -----
export async function listAthletes() {
  const res = await api.get<Paginated<CoachAthlete> | CoachAthlete[]>('/api/accounts/coach/athletes/');
  const d = res.data as Paginated<CoachAthlete>;
  return d.results ?? (res.data as CoachAthlete[]);
}
export async function addAthlete(athlete_email: string, notes?: string) {
  const res = await api.post<CoachAthlete>('/api/accounts/coach/athletes/', { athlete_email, notes: notes ?? '' });
  return res.data;
}
export async function removeAthlete(id: number) {
  return api.delete(`/api/accounts/coach/athletes/${id}/`);
}
export async function getAthleteWatchlist(id: number) {
  const res = await api.get<{ athlete: string; watchlist: WatchlistItem[] }>(
    `/api/accounts/coach/athletes/${id}/watchlist/`
  );
  return res.data;
}

// ----- Parent / Children -----
export async function listChildren() {
  const res = await api.get<import('../types').ParentChild[]>('/api/auth/children/');
  // DRF may return paginated or array
  const d = res.data as any;
  return d.results ?? (res.data as import('../types').ParentChild[]);
}
export async function listChildProfiles(childUserId: number) {
  // The backend returns profiles belonging to the authenticated user.
  // For a parent viewing child profiles, we use the admin-panel endpoint
  // or a dedicated query param. Fallback: profiles are loaded from the child's own session.
  // Since we can't auth as the child, we use the parent-child endpoint that includes child data.
  const res = await api.get<Paginated<PlayerProfile> | PlayerProfile[]>(
    `/api/players/profiles/?user_id=${childUserId}`
  );
  const d = res.data as Paginated<PlayerProfile>;
  return d.results ?? (res.data as PlayerProfile[]);
}
export async function listChildWatchlist(childUserId: number) {
  const res = await api.get<Paginated<WatchlistItem> | WatchlistItem[]>(
    `/api/watchlist/?user_id=${childUserId}`
  );
  const d = res.data as Paginated<WatchlistItem>;
  return d.results ?? (res.data as WatchlistItem[]);
}
export async function listChildRegistrations(childUserId: number) {
  const res = await api.get<any>(`/api/registrations/?user_id=${childUserId}`);
  const d = res.data;
  return d.results ?? d;
}

export async function createChildProfile(linkId: number, data: Partial<PlayerProfile>) {
  const res = await api.post<PlayerProfile>(`/api/auth/children/${linkId}/profile/`, data);
  return res.data;
}
export async function createChildWithProfile(
  accountData: { full_name: string; email: string; password: string; password_confirm: string },
  profileData: {
    display_name?: string;
    birth_year: number;
    gender: 'M' | 'F' | '';
    home_state: string;
    home_city?: string;
    federation?: number | null;
    travel_states?: string[];
    competitive_level: string;
  },
): Promise<ParentChild> {
  const res = await api.post<ParentChild>('/api/auth/children/create-with-profile/', {
    ...accountData,
    profile: profileData,
  });
  return res.data;
}
export async function removeChild(linkId: number) {
  return api.delete(`/api/auth/children/${linkId}/remove/`);
}
export async function sendChildPasswordReset(linkId: number) {
  await api.post(`/api/auth/children/${linkId}/reset-password/`);
}

export async function updateChildAccount(linkId: number, data: { full_name?: string; email?: string }) {
  const res = await api.patch<ParentChild>(`/api/auth/children/${linkId}/update-account/`, data);
  return res.data;
}
export async function createChildAccount(data: { full_name: string; email: string; password: string; password_confirm: string; phone?: string }): Promise<ParentChild> {
  const res = await api.post<ParentChild>('/api/auth/children/', data);
  return res.data;
}

// ----- Tênis Integrado -----

export async function fetchTiData(profileId: number, refresh = false): Promise<TiData> {
  const url = `/api/players/profiles/${profileId}/ti-data/${refresh ? '?refresh=1' : ''}`;
  const res = await api.get<TiData>(url);
  return res.data;
}

export async function syncTiData(profileId: number): Promise<{ detail: string; results_count: number; rankings_count: number }> {
  const res = await api.post(`/api/players/profiles/${profileId}/ti-sync/`);
  invalidateProfilesCache();
  return res.data;
}

// ----- UTR (Universal Tennis Rating) -----

export async function searchUtr(profileId: number, name: string): Promise<UtrSearchResult> {
  const res = await api.get<UtrSearchResult>(
    `/api/players/profiles/${profileId}/utr-search/?q=${encodeURIComponent(name)}`,
  );
  return res.data;
}

export async function linkUtr(
  profileId: number,
  candidate: Pick<UtrCandidate, 'utr_player_id' | 'display_name' | 'singles_utr' | 'doubles_utr' | 'profile_url'>,
): Promise<PlayerProfile> {
  const res = await api.post<PlayerProfile>(`/api/players/profiles/${profileId}/utr-link/`, {
    utr_player_id: candidate.utr_player_id,
    display_name: candidate.display_name,
    singles_utr: candidate.singles_utr ?? '',
    doubles_utr: candidate.doubles_utr ?? '',
    profile_url: candidate.profile_url,
  });
  invalidateProfilesCache();
  return res.data;
}

export async function unlinkUtr(profileId: number): Promise<void> {
  await api.post(`/api/players/profiles/${profileId}/utr-unlink/`);
  invalidateProfilesCache();
}

export async function syncUtr(profileId: number): Promise<{ utr_singles: string; utr_doubles: string }> {
  const res = await api.post(`/api/players/profiles/${profileId}/utr-sync/`);
  invalidateProfilesCache();
  return res.data;
}

// ----- Dependent Invites -----
export async function searchPlayersForInvite(q: string) {
  const res = await api.get<PlayerSearchResult[]>(`/api/auth/children/search-players/?q=${encodeURIComponent(q)}`);
  return res.data;
}
export async function sendDependentInvite(inviteeId: number) {
  const res = await api.post<DependentInvite>('/api/auth/children/invite/', { invitee_id: inviteeId });
  return res.data;
}
export async function listSentInvites() {
  const res = await api.get<DependentInvite[]>('/api/auth/children/sent-invites/');
  return res.data;
}
export async function cancelDependentInvite(inviteId: number) {
  return api.delete(`/api/auth/children/sent-invites/${inviteId}/`);
}
export async function listReceivedInvites() {
  const res = await api.get<DependentInvite[]>('/api/auth/invites/');
  return res.data;
}
export async function respondDependentInvite(inviteId: number, action: 'accept' | 'decline') {
  const res = await api.post<{ detail: string; link_id?: number }>(`/api/auth/invites/${inviteId}/respond/`, { action });
  return res.data;
}

// ----- LGPD -----
export async function requestDataExport() {
  const res = await api.get<object>('/api/auth/data-export/');
  return res.data;
}

// ----- Alerts -----
export async function listAlerts() {
  const res = await api.get<{ count: number; results: Alert[] } | Paginated<Alert>>('/api/alerts/unread/');
  const d = res.data as Paginated<Alert>;
  return d.results ?? (res.data as { count: number; results: Alert[] }).results;
}
export async function unreadAlerts() {
  const res = await api.get<{ count: number; results: Alert[] } | Paginated<Alert>>(
    '/api/alerts/unread/',
  );
  const d = res.data as Paginated<Alert>;
  return d.results ?? (res.data as { count: number; results: Alert[] }).results;
}
export async function markAlertRead(id: number) {
  return api.post(`/api/alerts/${id}/mark-read/`);
}
export async function markAllAlertsRead() {
  return api.post('/api/alerts/mark-all-read/');
}
