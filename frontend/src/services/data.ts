import api from './api';
import { Alert, CoachAthlete, Paginated, ParentChild, PlayerCategory, PlayerProfile, WatchlistItem } from '../types';

// ----- Players -----
export async function listProfiles() {
  const res = await api.get<Paginated<PlayerProfile> | PlayerProfile[]>('/api/players/profiles/');
  const d = res.data as Paginated<PlayerProfile>;
  return d.results ?? (res.data as PlayerProfile[]);
}
export async function getProfile(id: number) {
  const res = await api.get<PlayerProfile>(`/api/players/profiles/${id}/`);
  return res.data;
}
export async function createProfile(data: Partial<PlayerProfile>) {
  const res = await api.post<PlayerProfile>('/api/players/profiles/', data);
  return res.data;
}
export async function updateProfile(id: number, data: Partial<PlayerProfile>) {
  const res = await api.patch<PlayerProfile>(`/api/players/profiles/${id}/`, data);
  return res.data;
}
export async function deleteProfile(id: number) {
  return api.delete(`/api/players/profiles/${id}/`);
}
export async function setPrimary(id: number) {
  return api.post(`/api/players/profiles/${id}/set_primary/`);
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
  await api.post(`/api/auth/children/${linkId}/password-reset/`);
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
  const res = await api.get<Paginated<Alert> | Alert[]>('/api/alerts/');
  const d = res.data as Paginated<Alert>;
  return d.results ?? (res.data as Alert[]);
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
