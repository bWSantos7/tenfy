export type Role = 'player' | 'coach' | 'parent' | 'admin';

// ── Tênis Integrado ──────────────────────────────────────────────────────────
export interface TiResultEntry {
  tournament?: string;
  date?: string;
  category?: string;
  round?: string;
  opponent?: string;
  outcome?: string;
  score?: string;
  position?: string;
  _raw?: Record<string, string>;
}

export interface TiRankingEntry {
  category?: string;
  modality?: string;
  federation?: string;
  position?: string;
  points?: string;
  class_label?: string;
  ranking_name?: string;
  _raw?: Record<string, string>;
}

export interface TiData {
  has_ti_id: boolean;
  ti_id?: string;
  source?: string;
  results_url?: string;
  rankings_url?: string;
  profile_url?: string;
  is_stale?: boolean;
  sync_error?: string | null;
  results: TiResultEntry[];
  rankings: TiRankingEntry[];
  results_synced_at?: string | null;
  rankings_synced_at?: string | null;
  detail?: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  avatar: string | null;
  role: Role;
  email_verified: boolean;
  consent_version: string;
  consented_at: string | null;
  marketing_consent: boolean;
  is_staff: boolean;
  created_at: string;
  managed_by_parent?: boolean;
  parent_info?: {
    id: number;
    full_name: string;
    email: string;
  } | null;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse extends AuthTokens {
  user: User;
  email_otp_sent?: boolean;
}

export interface Organization {
  id: number;
  name: string;
  short_name: string;
  type: 'confederation' | 'federation' | 'platform' | 'club' | 'media';
  website_url: string;
  logo_url: string;
  state: string;
  description: string;
  is_active: boolean;
}

export interface PlayerCategory {
  id: number;
  taxonomy: string;
  code: string;
  label_ptbr: string;
  gender_scope: 'M' | 'F' | 'X' | '*';
  min_age: number | null;
  max_age: number | null;
  class_level: number | null;
  description: string;
}

export interface PlayerProfileCategory {
  id: number;
  category: number;
  category_detail: PlayerCategory;
  is_primary: boolean;
  confidence: string;
}

export interface PlayerProfile {
  id: number;
  user_id: number;
  display_name: string;
  birth_year: number | null;
  birth_date: string | null;
  gender: 'M' | 'F' | '';
  home_state: string;
  home_city: string;
  travel_radius_km: number;
  travel_states: string[];
  competitive_level: 'beginner' | 'amateur' | 'federated' | 'youth' | 'pro';
  dominant_hand: 'R' | 'L' | '';
  tennis_class: string;
  preferred_modality: string;
  is_primary: boolean;
  external_ids: Record<string, unknown>;
  categories: PlayerProfileCategory[];
  sporting_age: number | null;
  created_at: string;
  updated_at: string;
}

export type TournamentStatus =
  | 'unknown' | 'announced' | 'open' | 'closing_soon'
  | 'closed' | 'draws_published' | 'in_progress'
  | 'finished' | 'canceled';

export interface TournamentEditionList {
  id: number;
  tournament: number;
  tournament_name: string;
  organization_name: string;
  organization_short: string;
  circuit: string;
  modality: string;
  /** True = youth/junior tournament; False = adult; null = not yet classified */
  is_youth: boolean | null;
  season_year: number;
  title: string;
  start_date: string | null;
  end_date: string | null;
  entry_open_at: string | null;
  entry_close_at: string | null;
  withdrawal_deadline_at: string | null;
  has_online_entry: boolean;
  status: TournamentStatus;
  dynamic_status: TournamentStatus;
  surface: string;
  venue_name: string | null;
  venue_city: string | null;
  venue_state: string | null;
  base_price_brl: string | null;
  official_source_url: string;
  source_name: string;
  fetched_at: string | null;
  data_confidence: 'low' | 'med' | 'high';
  categories_count: number;
  eligibility?: {
    compatible_count: number;
    unknown_count: number;
    total_count: number;
  };
}

export interface TournamentLink {
  id: number;
  link_type: 'registration' | 'regulation' | 'results' | 'draws' | 'other';
  url: string;
  label: string;
  is_official: boolean;
  source_name: string;
  fetched_at: string | null;
}

export interface TournamentCategory {
  id: number;
  source_category_text: string;
  normalized_category: number | null;
  normalized_category_detail: PlayerCategory | null;
  price_brl: string | null;
  max_participants: number | null;
  visibility_order: number;
  notes: string;
}

export type RegistrationStatus = 'confirmed' | 'waiting_list' | 'pending_payment' | 'withdrawn';
export type PaymentStatus = 'pending' | 'paid' | 'waived' | 'refunded';

export interface TournamentRegistration {
  id: number;
  edition_id: number;
  edition_title: string;
  edition_start_date: string | null;
  edition_end_date: string | null;
  edition_status: string;
  category_text: string | null;
  max_participants: number | null;
  registered_at: string;
  ranking_position: number | null;
  payment_status: PaymentStatus;
  payment_status_label: string;
  payment_confirmed_at: string | null;
  is_withdrawn: boolean;
  withdrawn_at: string | null;
  slot_position: number | null;
  in_draw: boolean | null;
  registration_status: RegistrationStatus;
  registration_status_label: string;
}

export interface TournamentChangeEvent {
  id: number;
  event_type: string;
  field_changes: Record<string, unknown>;
  detected_at: string;
}

export interface TournamentEditionDetail extends TournamentEditionList {
  external_id: string;
  price_notes: string;
  reviewed_at: string | null;
  reviewed_by_email: string | null;
  is_manual_override: boolean;
  raw_content_hash: string;
  tournament_detail: {
    id: number;
    canonical_name: string;
    organization_detail: Organization;
    circuit: string;
    modality: string;
    description: string;
  };
  venue_detail: null | {
    id: number;
    name: string;
    city: string;
    state: string;
    address: string;
    latitude: number | null;
    longitude: number | null;
  };
  categories: TournamentCategory[];
  links: TournamentLink[];
  change_events: TournamentChangeEvent[];
}

export type EligibilityStatus = 'compatible' | 'incompatible' | 'unknown';
export type RankingCheck = 'not_applicable' | 'unknown' | 'within_cutoff' | 'beyond_cutoff';

export interface EligibilityResult {
  status: EligibilityStatus;
  reasons: string[];
  rule_version_id: number | null;
  category_code: string | null;
  category_label: string | null;
  ranking_check?: RankingCheck;
  ranking_note?: string;
}

export interface EditionEligibility {
  edition_id: number;
  profile_id: number;
  sporting_age: number | null;
  total_count: number;
  compatible_count: number;
  incompatible_count: number;
  unknown_count: number;
  categories: Array<{
    tournament_category_id: number;
    source_text: string;
    price_brl: string | null;
    result: EligibilityResult;
  }>;
}

export interface TournamentResult {
  id: number;
  category_played: string;
  position: number | null;
  wins: number;
  losses: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: number;
  edition: number;
  edition_detail: TournamentEditionList;
  profile: number | null;
  user_status: 'none' | 'intended' | 'registered_declared' | 'withdrawn' | 'completed';
  notes: string;
  alert_on_deadline: boolean;
  alert_on_changes: boolean;
  alert_on_draws: boolean;
  result: TournamentResult | null;
  created_at: string;
  updated_at: string;
}

export interface Alert {
  id: number;
  kind: 'deadline' | 'change' | 'draws' | 'canceled' | 'other';
  channel: 'in_app' | 'email' | 'push';
  status: 'pending' | 'sent' | 'failed' | 'read';
  title: string;
  body: string;
  payload: Record<string, unknown>;
  edition: number | null;
  edition_title: string | null;
  edition_start_date: string | null;
  edition_official_url: string | null;
  dispatched_at: string | null;
  read_at: string | null;
  dedup_key: string;
  created_at: string;
}

export interface CoachAthlete {
  id: number;
  athlete_detail: {
    id: number;
    email: string;
    full_name: string;
    avatar: string | null;
    role: Role;
  };
  is_active: boolean;
  notes: string;
  created_at: string;
}

export interface ParentChild {
  id: number;
  child: number;
  child_detail: {
    id: number;
    email: string;
    full_name: string;
    avatar: string | null;
    role: Role;
  };
  is_active: boolean;
  created_at: string;
}

export interface PlayerSearchResult {
  id: number;
  full_name: string;
  email: string;
  avatar: string | null;
  role: Role;
}

export type DependentInviteStatus = 'pending' | 'accepted' | 'declined' | 'canceled' | 'expired';

export interface DependentInvite {
  id: number;
  parent: number;
  invitee: number;
  parent_detail: { id: number; full_name: string; email: string; avatar: string | null };
  invitee_detail: { id: number; full_name: string; email: string; avatar: string | null };
  status: DependentInviteStatus;
  is_expired: boolean;
  expires_at: string;
  responded_at: string | null;
  created_at: string;
}

export interface Paginated<T> {
  count: number;
  total_pages?: number;
  current_page?: number;
  page_size?: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface FederationEntry {
  id: number;
  category_text: string;
  player_name: string;
  player_external_id: string;
  ranking_position: number | null;
  payment_status: 'paid' | 'pending' | 'unknown';
  payment_status_label: string;
  source: string;
  source_label: string;
  source_url: string;
  confidence: 'high' | 'medium' | 'low';
  removed_or_replaced: boolean;
  replacement_reason: string;
  player_country_name: string;
  player_country_code: string;
  notes: string;
  synced_at: string;
  slot_position: number | null;
  in_draw: boolean | null;
  status: 'confirmed' | 'waiting_list' | 'pending_payment' | 'removed' | 'registered';
  status_label: string;
}

export interface FederationCategoryGroup {
  category_text: string;
  max_participants: number | null;
  summary: {
    total: number;
    paid: number;
    pending: number;
    in_draw: number;
    waiting_list: number;
    removed: number;
    total_slots: number | null;
    filled_slots: number;
    remaining_slots: number | null;
  };
  entries: FederationEntry[];
}

export interface FederationRegistrationList {
  edition_id: number;
  edition_title: string;
  categories: FederationCategoryGroup[];
}
