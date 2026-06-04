import api from './api';
import { Alert, CoachAthlete, DependentInvite, Paginated, ParentChild, PlayerCategory, PlayerProfile, PlayerSearchResult, TiData, WatchlistItem } from '../types';

// ----- Players -----
// Shared profiles cache. listProfiles() is called from several pages/components
// (Home, Perfil, Resultados, Torneios, Detalhe...) as the user navigates.
//
// Two layers, both safe:
//   1. In-flight dedup — collapses concurrent identical GETs into one request.
//   2. Short TTL cache — serves the same profiles across quick navigations
//      without re-fetching. Invalidated on every profile mutation, so it never
//      hides a change the user just made.
//
// Pass { force: true } to bypass the cache when fresh data is mandatory (e.g.
// after a UTR/TI sync that mutates the profile out-of-band).
const PROFILES_TTL_MS = 30_000;
let _profilesInFlight: Promise<PlayerProfile[]> | null = null;
let _profilesCache: { data: PlayerProfile[]; at: number } | null = null;

/** Drop the cached profiles so the next listProfiles() re-fetches. */
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

// ----- Parent / Children -----

export async function listChildren(): Promise<ParentChild[]> {
  const res = await api.get<Paginated<ParentChild> | ParentChild[]>('/api/auth/children/');
  const d = res.data as Paginated<ParentChild>;
  return d.results ?? (res.data as ParentChild[]);
}

export async function removeChild(linkId: number): Promise<void> {
  await api.delete(`/api/auth/children/${linkId}/remove/`);
}

export async function updateChildAccount(linkId: number, data: { full_name?: string; email?: string }): Promise<import('../types').ParentChild> {
  const res = await api.patch<import('../types').ParentChild>(`/api/auth/children/${linkId}/update-account/`, data);
  return res.data;
}

export async function listChildProfiles(childUserId: number): Promise<PlayerProfile[]> {
  const res = await api.get<Paginated<PlayerProfile> | PlayerProfile[]>(`/api/players/profiles/?user_id=${childUserId}`);
  const d = res.data as Paginated<PlayerProfile>;
  return d.results ?? (res.data as PlayerProfile[]);
}

export async function listChildWatchlist(childUserId: number): Promise<WatchlistItem[]> {
  const res = await api.get<Paginated<WatchlistItem> | WatchlistItem[]>(`/api/watchlist/?user_id=${childUserId}`);
  const d = res.data as Paginated<WatchlistItem>;
  return d.results ?? (res.data as WatchlistItem[]);
}

export async function createChildProfile(linkId: number, data: Partial<PlayerProfile>): Promise<PlayerProfile> {
  const res = await api.post<PlayerProfile>(`/api/auth/children/${linkId}/profile/`, data);
  return res.data;
}

export async function createChildAccount(
  accountData: { full_name: string; email: string; password: string; password_confirm: string },
): Promise<ParentChild> {
  const res = await api.post<ParentChild>('/api/auth/children/', accountData);
  return res.data;
}

export async function createChildWithProfile(
  accountData: { full_name: string; email: string; password: string; password_confirm: string },
  profileData: Partial<PlayerProfile>,
): Promise<{ user: import('../types').User; profile: PlayerProfile }> {
  const res = await api.post('/api/auth/children/create-with-profile/', { ...accountData, profile: profileData });
  return res.data;
}

export async function sendChildPasswordReset(linkId: number): Promise<void> {
  await api.post(`/api/auth/children/${linkId}/reset-password/`);
}

// ----- UTR -----

export async function searchUtr(profileId: number, name: string): Promise<{ candidates: import('../types').UtrCandidate[] }> {
  const res = await api.get(`/api/players/profiles/${profileId}/utr-search/?q=${encodeURIComponent(name)}`);
  return res.data;
}

export async function linkUtr(profileId: number, candidate: import('../types').UtrCandidate): Promise<void> {
  await api.post(`/api/players/profiles/${profileId}/utr-link/`, {
    utr_player_id: candidate.utr_player_id,
    display_name: candidate.display_name,
    singles_utr: candidate.singles_utr ?? '',
    doubles_utr: candidate.doubles_utr ?? '',
    profile_url: candidate.profile_url,
  });
  invalidateProfilesCache();
}

export async function unlinkUtr(profileId: number): Promise<void> {
  await api.post(`/api/players/profiles/${profileId}/utr-unlink/`);
  invalidateProfilesCache();
}

export async function syncUtr(profileId: number): Promise<void> {
  await api.post(`/api/players/profiles/${profileId}/utr-sync/`);
  invalidateProfilesCache();
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

// ----- Dependent Invites -----

export async function searchPlayersForInvite(q: string): Promise<PlayerSearchResult[]> {
  const res = await api.get<PlayerSearchResult[]>(`/api/auth/children/search-players/?q=${encodeURIComponent(q)}`);
  return res.data;
}

export async function sendDependentInvite(inviteeId: number): Promise<DependentInvite> {
  const res = await api.post<DependentInvite>('/api/auth/children/invite/', { invitee_id: inviteeId });
  return res.data;
}

export async function listSentInvites(): Promise<DependentInvite[]> {
  const res = await api.get<DependentInvite[]>('/api/auth/children/sent-invites/');
  return res.data;
}

export async function cancelDependentInvite(inviteId: number): Promise<void> {
  await api.delete(`/api/auth/children/sent-invites/${inviteId}/`);
}

export async function listReceivedInvites(): Promise<DependentInvite[]> {
  const res = await api.get<DependentInvite[]>('/api/auth/invites/');
  return res.data;
}

export async function respondDependentInvite(inviteId: number, action: 'accept' | 'decline'): Promise<{ detail: string; link_id?: number }> {
  const res = await api.post<{ detail: string; link_id?: number }>(`/api/auth/invites/${inviteId}/respond/`, { action });
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

// ----- LGPD -----
export async function requestDataExport(): Promise<object> {
  const res = await api.get<object>('/api/auth/data-export/');
  return res.data;
}
