import api from './api';
import {
  EditionEligibility,
  Paginated,
  TournamentEditionDetail,
  TournamentEditionList,
  TournamentChangeEvent,
} from '../types';

export interface TournamentFilters {
  q?: string;
  state?: string;
  city?: string;
  from_date?: string;
  to_date?: string;
  status?: string;
  modality?: string;
  circuit?: string;
  surface?: string;
  organization?: number;
  organization_slug?: string;
  category?: string;
  category_id?: number;
  category_code?: string;
  include_category_up?: boolean | string;
  near_profile?: number;
  /** Locked filter derived from active profile's competitive_level. Not user-editable. */
  player_level?: string;
  page?: number;
  page_size?: number;
  ordering?: string;
}

export interface OrganizationOption {
  id: number;
  name: string;
  short_name: string;
}

export async function listOrganizations(): Promise<OrganizationOption[]> {
  try {
    const res = await api.get<
      OrganizationOption[] | { count: number; results: OrganizationOption[] }
    >('/api/sources/organizations/');
    if (Array.isArray(res.data)) return res.data;
    const paged = res.data as { results?: OrganizationOption[] };
    if (Array.isArray(paged.results)) return paged.results;
  } catch (err) {
    console.warn('[listOrganizations] falhou ao carregar organizações:', err);
  }
  return [];
}

function qs(params: Record<string, unknown>): string {
  const out: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    out.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return out.length ? `?${out.join('&')}` : '';
}

export async function listEditions(filters: TournamentFilters = {}) {
  const res = await api.get<Paginated<TournamentEditionList>>(
    `/api/tournaments/editions/${qs(filters as Record<string, unknown>)}`,
  );
  return res.data;
}

export async function getEdition(id: number) {
  const res = await api.get<TournamentEditionDetail>(`/api/tournaments/editions/${id}/`);
  return res.data;
}

export async function closingSoon(days = 14, filters: Record<string, string> = {}) {
  const params = new URLSearchParams({ days: String(days), ...filters });
  const res = await api.get<Paginated<TournamentEditionList> | TournamentEditionList[]>(
    `/api/tournaments/editions/closing_soon/?${params}`,
  );
  const d = res.data as Paginated<TournamentEditionList>;
  return d.results ?? (res.data as TournamentEditionList[]);
}

export async function compatibleForProfile(profileId: number, filters: TournamentFilters = {}) {
  const res = await api.get<{ count: number; results: TournamentEditionList[] }>(
    `/api/tournaments/editions/compatible/${qs({ ...(filters as Record<string, unknown>), profile_id: profileId })}`,
  );
  return res.data;
}

export async function editionHistory(id: number) {
  const res = await api.get<TournamentChangeEvent[]>(
    `/api/tournaments/editions/${id}/history/`,
  );
  return res.data;
}

export async function calendar(filters: TournamentFilters = {}) {
  const res = await api.get<Array<{ month: string; items: TournamentEditionList[] }>>(
    `/api/tournaments/editions/calendar/${qs(filters as Record<string, unknown>)}`,
  );
  return res.data;
}

export async function evaluateEdition(editionId: number, profileId?: number) {
  const url = profileId
    ? `/api/eligibility/evaluate/${editionId}/?profile_id=${profileId}`
    : `/api/eligibility/evaluate/${editionId}/`;
  const res = await api.get<EditionEligibility>(url);
  return res.data;
}

export interface ConflictPair {
  edition_a: { id: number; title: string; start_date: string; end_date: string };
  edition_b: { id: number; title: string; start_date: string; end_date: string };
}

export async function checkConflicts(ids: number[]): Promise<{ conflicts: ConflictPair[]; has_conflicts: boolean }> {
  const res = await api.post<{ conflicts: ConflictPair[]; has_conflicts: boolean }>(
    '/api/tournaments/editions/check_conflicts/',
    { ids },
  );
  return res.data;
}
