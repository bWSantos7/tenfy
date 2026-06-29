import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, Filter, Loader2, X, MapPin, List, Calendar, ChevronLeft, ChevronRight, ChevronDown, Check, GitCompareArrows, CheckSquare, Square, Sparkles } from 'lucide-react';
import { TournamentEditionList } from '../types';
import {
  listEditions,
  listOrganizations,
  listCountries,
  calendar as calendarApi,
  compatibleForProfile,
  TournamentFilters,
  OrganizationOption,
} from '../services/tournaments';
import { resolveCountry } from '../utils/country';
import { listProfiles } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { SearchableSelect } from '../components/SearchableSelect';
import { pickBestProfile } from '../utils/profile';
import { useAuth } from '../contexts/AuthContext';
import { getActiveProfileId } from '../utils/activeProfile';

const STATES = [
  '', 'SP','RJ','MG','RS','SC','PR','BA','PE','CE','DF','GO','ES',
  'MT','MS','PA','AM','MA','RN','PB','AL','SE','PI','TO','RO','RR','AP','AC',
];

const STATUS_OPTS = [
  { v: '', l: 'Todos' },
  { v: 'open', l: 'Abertas' },
  { v: 'closing_soon', l: 'Encerrando' },
  { v: 'closed', l: 'Inscrições encerradas' },
  { v: 'announced', l: 'Anunciados' },
  { v: 'in_progress', l: 'Em andamento' },
  { v: 'draws_published', l: 'Chaves publicadas' },
  { v: 'finished', l: 'Finalizados' },
  { v: 'canceled', l: 'Cancelados' },
];

// Status visíveis por padrão na página Torneios (quando o usuário não filtra):
// somente Anunciados, Abertas, Encerrando e Em Andamento. Inscrições encerradas,
// Finalizados, Cancelados, Chaves publicadas e quaisquer outros ficam ocultos.
const DEFAULT_VISIBLE_STATUSES = 'announced,open,closing_soon,in_progress';

const MONTHS_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const WEEKDAYS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
const TODAY = new Date().toISOString().slice(0, 10);

// Mesma ordem do backend (_build_dynamic_priority): Abertas, Encerrando, Anunciados,
// Em Andamento. Mantém a página recebida coerente com a paginação do servidor.
const STATUS_SORT_PRIORITY: Record<string, number> = {
  open: 0,
  closing_soon: 0,
  announced: 1,
  unknown: 1,
  in_progress: 2,
  draws_published: 2,
  closed: 3,
  finished: 4,
  canceled: 5,
};

function groupByMonth(items: TournamentEditionList[]) {
  const map = new Map<string, TournamentEditionList[]>();
  for (const item of items) {
    const key = item.start_date ? item.start_date.slice(0, 7) : 'sem-data';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(item);
  }
  return Array.from(map.entries())
    .map(([key, its]) => {
      const [year, mon] = key.split('-');
      const label = key === 'sem-data' ? 'Sem data definida' : `${MONTHS_PT[Number(mon) - 1]} ${year}`;
      return { key, label, items: its };
    })
    .sort((a, b) => {
      if (a.key === 'sem-data') return 1;
      if (b.key === 'sem-data') return -1;
      return a.key.localeCompare(b.key);
    });
}

// Groups for section headers — uses dynamic_status when available
function getStatusGroup(status: string): string {
  if (status === 'open' || status === 'closing_soon') return 'open';
  if (status === 'announced') return 'announced';
  if (status === 'in_progress' || status === 'draws_published') return 'in_progress';
  if (status === 'closed') return 'closed';
  return 'other';
}

const GROUP_LABELS: Record<string, string> = {
  open: 'Inscrições Abertas',
  announced: 'Anunciados',
  in_progress: 'Em Andamento',
  closed: 'Encerradas',
  other: 'Outros',
};

function sortTournaments(list: TournamentEditionList[]): TournamentEditionList[] {
  return [...list].sort((a, b) => {
    const pa = STATUS_SORT_PRIORITY[(a.dynamic_status ?? a.status) ?? 'unknown'] ?? 5;
    const pb = STATUS_SORT_PRIORITY[(b.dynamic_status ?? b.status) ?? 'unknown'] ?? 5;
    if (pa !== pb) return pa - pb;
    return (a.start_date || '').localeCompare(b.start_date || '');
  });
}

type ViewMode = 'list' | 'calendar';

// Filtro de status em "caixa" (como os demais filtros), porém com multi-seleção via
// checkboxes num dropdown. Sem seleção = "Todos" (a visão aplica seu padrão de ocultação).
const StatusFilterSelect: React.FC<{
  options: { v: string; l: string }[];
  selected: Set<string>;
  onToggle: (v: string) => void;
  onClear: () => void;
}> = ({ options, selected, onToggle, onClear }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const summary = selected.size === 0
    ? 'Todos'
    : options.filter((o) => selected.has(o.v)).map((o) => o.l).join(', ');

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="input-base w-full flex items-center justify-between gap-2 text-left"
        data-testid="filter-status"
      >
        <span className={`truncate ${selected.size === 0 ? 'text-text-muted' : ''}`}>{summary}</span>
        <ChevronDown className={`w-4 h-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-xl border border-border-subtle bg-bg-card shadow-lg p-1 max-h-64 overflow-auto">
          {options.map((o) => {
            const checked = selected.has(o.v);
            return (
              <button
                key={o.v}
                type="button"
                onClick={() => onToggle(o.v)}
                aria-pressed={checked}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-left hover:bg-bg-base"
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${checked ? 'bg-accent-neon border-accent-neon' : 'border-border-subtle'}`}>
                  {checked && <Check className="w-3 h-3 text-bg-base" />}
                </span>
                <span className="flex-1">{o.l}</span>
              </button>
            );
          })}
          {selected.size > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="w-full text-xs text-accent-blue hover:underline px-2 py-1.5 text-left"
            >
              Limpar status
            </button>
          )}
        </div>
      )}
    </div>
  );
};

const FILTER_SESSION_KEY = 'tenfy_tournament_filters';

interface PersistedFilters {
  filters: TournamentFilters;
  q: string;
  nearMe: boolean;
  showFilters: boolean;
  page: number;
}

function loadSavedFilters(): PersistedFilters | null {
  try {
    const raw = sessionStorage.getItem(FILTER_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveFilters(state: PersistedFilters) {
  try { sessionStorage.setItem(FILTER_SESSION_KEY, JSON.stringify(state)); } catch {}
}

export const TournamentsPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // Compatible mode: "Ver todos" from the home "Compatíveis com você" section.
  // Lists the full compatibility-filtered set for the active profile (federation,
  // category, modality, location), not the generic catalogue.
  const compatMode = searchParams.get('compat') === '1';
  const saved = useRef<PersistedFilters | null>(loadSavedFilters());

  const [viewMode, setViewMode] = useState<ViewMode>('list');

  // Compare mode
  const [compareMode, setCompareMode] = useState(false);
  const [selectedCompare, setSelectedCompare] = useState<Set<number>>(new Set());

  function toggleCompareMode() {
    setCompareMode((v) => !v);
    setSelectedCompare(new Set());
  }

  function toggleCompareSelect(id: number) {
    setSelectedCompare((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else if (next.size < 4) { next.add(id); }
      return next;
    });
  }

  function handleCompare() {
    if (selectedCompare.size < 2) return;
    navigate(`/comparar?ids=${Array.from(selectedCompare).join(',')}`);
  }

  // List state
  const [items, setItems] = useState<TournamentEditionList[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(saved.current?.page ?? 1);

  // Calendar state
  const [calendarMap, setCalendarMap] = useState<Record<string, TournamentEditionList[]>>({});
  const [calMonth, setCalMonth] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Filters — restored from session on mount
  const [filters, setFilters] = useState<TournamentFilters>(saved.current?.filters ?? { status: '', state: '' });
  const [showFilters, setShowFilters] = useState(saved.current?.showFilters ?? false);
  const [q, setQ] = useState(saved.current?.q ?? '');
  const [nearMe, setNearMe] = useState(saved.current?.nearMe ?? false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);
  // Locked constraints from the active profile — not user-editable in the filter UI
  const [profileModality, setProfileModality] = useState<string>('');
  const [profileLevel, setProfileLevel] = useState<string>('');
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);
  const [countryCodes, setCountryCodes] = useState<string[]>([]);
  // Bumped on 'profiles-changed' (e.g. federation edited in settings) to force a
  // fresh reload of the active profile + listing without a hard refresh.
  const [refreshKey, setRefreshKey] = useState(0);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onProfilesChanged = () => setRefreshKey((k) => k + 1);
    window.addEventListener('profiles-changed', onProfilesChanged);
    return () => window.removeEventListener('profiles-changed', onProfilesChanged);
  }, []);

  // Country options for the filter dropdown, grouped by name so a country that
  // appears under both IOC (ITF) and ISO (COSAT) codes — e.g. Chile CHI/CHL —
  // shows once and filters all its codes. Option value = comma-joined codes.
  const countryOptions = useMemo(() => {
    const byName = new Map<string, string[]>();
    for (const code of countryCodes) {
      const info = resolveCountry(code);
      // Skip codes we can't resolve to a real country name — never show raw codes.
      if (!info) continue;
      const arr = byName.get(info.name) || [];
      arr.push(code);
      byName.set(info.name, arr);
    }
    const opts = [...byName.entries()].map(([name, codes]) => ({
      code: codes.join(','),
      name,
      isBrazil: codes.includes('BRA'),
    }));
    opts.sort((a, b) => {
      if (a.isBrazil) return -1;
      if (b.isBrazil) return 1;
      return a.name.localeCompare(b.name, 'pt-BR');
    });
    return opts;
  }, [countryCodes]);

  useEffect(() => {
    // force:true → ignora o cache em memória quando algo mudou (refreshKey),
    // garantindo a federação nova logo após editar nas configurações.
    listProfiles({ force: refreshKey > 0 }).then((profiles) => {
      const list = Array.isArray(profiles) ? profiles : (profiles as any).results ?? [];
      let primary = null;
      if (user?.role === 'parent' && user.id) {
        const activeId = getActiveProfileId(user.id);
        if (activeId) primary = list.find((p: any) => p.id === activeId) ?? null;
      }
      if (!primary) primary = pickBestProfile(list);
      if (primary) {
        setPrimaryProfileId(primary.id);
        const mod = primary.preferred_modality || '';
        const level = (primary as any).competitive_level || '';
        setProfileModality(mod);
        setProfileLevel(level);
        // Both modality and competitive_level are hard constraints locked to the
        // active profile — always apply them, overriding any saved session value.
        setFilters((f) => ({
          ...f,
          ...(mod ? { modality: mod } : {}),
          ...(level ? { player_level: level } : {}),
        }));
      }
    }).catch(() => {});
    listOrganizations().then(setOrganizations).catch(() => setOrganizations([]));
    listCountries().then(setCountryCodes).catch(() => setCountryCodes([]));
  }, [user?.id, user?.role, refreshKey]);

  // Auto-apply text search after 400ms debounce
  useEffect(() => {
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      setFilters((f) => ({ ...f, q: q.trim() || undefined }));
      setPage(1);
    }, 400);
    return () => { if (searchDebounce.current) clearTimeout(searchDebounce.current); };
  }, [q]);

  // Status selecionados (multi-seleção). filters.status é uma lista separada por vírgula;
  // vazio = padrão da agenda (ativos, sem encerrados/finalizados/cancelados).
  const selectedStatuses = useMemo(
    () => new Set((filters.status || '').split(',').filter(Boolean)),
    [filters.status],
  );

  const hasAnyFilter = useMemo(
    () => !!(
      filters.status || filters.state || filters.q
      // Modality and player_level are locked constraints, not user-applied filters.
      || (filters.modality && filters.modality !== profileModality)
      || filters.from_date || filters.to_date
      || filters.organization || filters.category || filters.country
    ),
    [filters, profileModality],
  );

  // Persist filters in sessionStorage so they survive navigation to detail and back
  useEffect(() => {
    saveFilters({ filters, q, nearMe, showFilters, page });
  }, [filters, q, nearMe, showFilters, page]);

  // Load list view
  useEffect(() => {
    if (viewMode !== 'list') return;
    let cancel = false;
    setLoading(true);

    // Compatible mode: full compatibility-filtered list for the active profile.
    if (compatMode && primaryProfileId) {
      compatibleForProfile(primaryProfileId, { ...filters, ...statusParams(), page, page_size: 20 } as TournamentFilters)
        .then((data) => {
          if (cancel) return;
          setItems(sortTournaments(data.results));
          setTotalPages(Math.max(1, Math.ceil((data.count || 0) / 20)));
        })
        .catch(() => setItems([]))
        .finally(() => { if (!cancel) setLoading(false); });
      return () => { cancel = true; };
    }

    const nearFilter = nearMe && primaryProfileId ? { near_profile: primaryProfileId } : {};
    const scopeFilter = primaryProfileId ? { profile_id: primaryProfileId } : {};
    listEditions({ ...filters, ...statusParams(), ...nearFilter, ...scopeFilter, page, page_size: 20, ordering: 'status_priority,start_date' })
      .then((data) => {
        if (cancel) return;
        setItems(sortTournaments(data.results));
        setTotalPages(data.total_pages || 1);
      })
      .catch(() => setItems([]))
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [filters, page, nearMe, primaryProfileId, viewMode, compatMode, refreshKey]);

  // Load calendar view
  useEffect(() => {
    if (viewMode !== 'calendar') return;
    let cancel = false;
    setLoading(true);
    const nearFilter = nearMe && primaryProfileId ? { near_profile: primaryProfileId } : {};
    const scopeFilter = primaryProfileId ? { profile_id: primaryProfileId } : {};
    calendarApi({ ...filters, ...statusParams(), ...nearFilter, ...scopeFilter })
      .then((months) => {
        if (cancel) return;
        const map: Record<string, TournamentEditionList[]> = {};
        months.forEach((m) => {
          m.items.forEach((ed) => {
            if (ed.start_date) {
              const key = ed.start_date.slice(0, 10);
              if (!map[key]) map[key] = [];
              map[key].push(ed);
            }
          });
        });
        setCalendarMap(map);
      })
      .catch(() => setCalendarMap({}))
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [filters, nearMe, primaryProfileId, viewMode, refreshKey]);

  function applySearch() {
    setPage(1);
    setFilters((f) => ({ ...f, q: q.trim() || undefined }));
  }

  function clearFilters() {
    setQ('');
    setFilters({
      status: '',
      state: '',
      ...(profileModality ? { modality: profileModality } : {}),
      ...(profileLevel ? { player_level: profileLevel } : {}),
    });
    setNearMe(false);
    setPage(1);
    try { sessionStorage.removeItem(FILTER_SESSION_KEY); } catch {}
  }

  function switchMode(mode: ViewMode) {
    setViewMode(mode);
    setSelectedDate(null);
    setPage(1);
  }

  // Alterna um status na multi-seleção (atualiza a lista separada por vírgula).
  function toggleStatus(v: string) {
    setPage(1);
    setFilters((f) => {
      const cur = new Set((f.status || '').split(',').filter(Boolean));
      if (cur.has(v)) cur.delete(v); else cur.add(v);
      return { ...f, status: Array.from(cur).join(',') };
    });
  }

  // Status enviado à API: seleção explícita do usuário ou, sem seleção, os 4 status
  // visíveis por padrão (Anunciados, Abertas, Encerrando, Em Andamento).
  function statusParams(): { status: string } {
    return { status: filters.status || DEFAULT_VISIBLE_STATUSES };
  }

  // Calendar helpers
  const year = calMonth.getFullYear();
  const month = calMonth.getMonth();
  const firstDayOfMonth = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  function dayKey(day: number) {
    return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }
  const selectedDayItems = selectedDate ? (calendarMap[selectedDate] ?? []) : [];

  return (
    <div className="space-y-4">
      {/* Header with view toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Torneios</h1>
          <p className="text-sm text-text-muted">Agregados de CBT, FPT e federações parceiras</p>
        </div>
        <div className="flex items-center gap-1">
          <div className="flex items-center gap-1 bg-bg-card border border-border-subtle rounded-xl p-1">
            <button
              onClick={() => switchMode('list')}
              title="Lista"
              className={`p-2 rounded-lg transition-colors ${viewMode === 'list' ? 'bg-accent-neon text-bg-base' : 'text-text-muted hover:text-text-primary'}`}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => switchMode('calendar')}
              title="Calendário"
              className={`p-2 rounded-lg transition-colors ${viewMode === 'calendar' ? 'bg-accent-neon text-bg-base' : 'text-text-muted hover:text-text-primary'}`}
            >
              <Calendar className="w-4 h-4" />
            </button>
          </div>
          {viewMode === 'list' && (
            <button
              onClick={toggleCompareMode}
              title={compareMode ? 'Sair do modo comparação' : 'Comparar torneios'}
              className={`p-2 rounded-xl border transition-colors ${
                compareMode
                  ? 'bg-accent-neon text-bg-base border-accent-neon'
                  : 'bg-bg-card border-border-subtle text-text-muted hover:text-text-primary'
              }`}
            >
              <GitCompareArrows className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Compatible-mode banner */}
      {compatMode && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-accent-neon/40 bg-accent-neon/5 px-3 py-2">
          <span className="flex items-center gap-1.5 text-sm text-accent-neon font-medium">
            <Sparkles className="w-4 h-4" />
            Mostrando apenas torneios compatíveis com o seu perfil
          </span>
          <button
            className="text-xs text-accent-blue hover:underline shrink-0"
            onClick={() => { setSearchParams({}); setPage(1); }}
          >
            Ver todos os torneios
          </button>
        </div>
      )}

      {/* Filters row */}
      <div className="flex items-center gap-2 flex-wrap">
        {primaryProfileId && (
          <button
            onClick={() => { setNearMe((v) => !v); setPage(1); }}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-sm font-medium transition-colors ${
              nearMe
                ? 'bg-accent-neon text-bg-base border-accent-neon'
                : 'bg-bg-card border-border-subtle text-text-secondary hover:text-text-primary'
            }`}
            title="Mostrar torneios dentro do seu raio de viagem"
          >
            <MapPin className="w-4 h-4" />
            Perto de mim
          </button>
        )}
      </div>

      {/* Search + filter toggle */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            className="input-base pl-10"
            placeholder="Buscar por nome, cidade..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && applySearch()}
            data-testid="tournaments-search"
          />
        </div>
        <button
          className="btn-secondary !px-3 relative"
          onClick={() => setShowFilters((v) => !v)}
          data-testid="tournaments-filter-toggle"
        >
          <Filter className="w-4 h-4" />
          {hasAnyFilter && (
            <span className="absolute -top-1 -right-1 bg-accent-neon w-2 h-2 rounded-full" />
          )}
        </button>
        {(hasAnyFilter || nearMe) && (
          <button
            className="text-xs text-accent-blue flex items-center gap-1 px-2 hover:underline shrink-0"
            onClick={clearFilters}
            title="Limpar todos os filtros"
          >
            <X className="w-3 h-3" /> Limpar
          </button>
        )}
      </div>

      {showFilters && (
        <div className="card space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <SearchableSelect
              label="UF"
              value={filters.state || ''}
              onChange={(v) => { setPage(1); setFilters((f) => ({ ...f, state: v })); }}
              options={STATES.map((s) => ({ value: s, label: s || 'Todos' }))}
              placeholder="Todos"
              allowClear
              data-testid="filter-state"
            />
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Status</label>
              <StatusFilterSelect
                options={STATUS_OPTS.filter((o) => o.v)}
                selected={selectedStatuses}
                onToggle={toggleStatus}
                onClear={() => { setPage(1); setFilters((f) => ({ ...f, status: '' })); }}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Data inicial (a partir de)</label>
              <input
                type="date"
                className="input-base"
                value={filters.from_date || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, from_date: e.target.value || undefined })); }}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Data final (até)</label>
              <input
                type="date"
                className="input-base"
                value={filters.to_date || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, to_date: e.target.value || undefined })); }}
              />
            </div>
            <p className="col-span-2 -mt-1 text-[11px] leading-snug text-text-muted">
              Filtra pela <strong className="font-semibold">data de início</strong> do torneio: mostra os torneios que começam dentro do período selecionado.
            </p>
            <SearchableSelect
              label="Entidade / fonte"
              value={filters.organization != null ? String(filters.organization) : ''}
              onChange={(v) => { setPage(1); setFilters((f) => ({ ...f, organization: v ? Number(v) : undefined })); }}
              options={[{ value: '', label: 'Todas' }, ...organizations.map((o) => ({ value: String(o.id), label: o.short_name || o.name }))]}
              placeholder="Todas"
              allowClear
            />
            {countryOptions.length > 0 && (
              <SearchableSelect
                label="País"
                value={filters.country ?? ''}
                onChange={(v) => { setPage(1); setFilters((f) => ({ ...f, country: v || undefined })); }}
                options={[{ value: '', label: 'Todos' }, ...countryOptions.map((c) => ({ value: c.code, label: c.name }))]}
                placeholder="Todos"
                allowClear
                data-testid="filter-country"
              />
            )}
            <div className="col-span-2">
              <label className="text-xs text-text-secondary mb-1 block">Categoria</label>
              <input
                className="input-base"
                placeholder="Ex.: 16M, GA, Gold M1, Sub-12"
                value={filters.category || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, category: e.target.value || undefined })); }}
              />
            </div>
          </div>
          {hasAnyFilter && (
            <button
              className="text-xs text-accent-blue flex items-center gap-1 hover:underline"
              onClick={clearFilters}
            >
              <X className="w-3 h-3" /> Limpar filtros
            </button>
          )}
        </div>
      )}

      {/* ─── LIST VIEW ─────────────────────────────────────────────────────── */}
      {viewMode === 'list' && (
        <>
          {loading ? (
            <div className="py-16 flex justify-center">
              <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="card text-center py-10 text-text-muted">
              Nenhum torneio encontrado com estes filtros.
            </div>
          ) : (
            <div data-testid="tournament-list">
              {compareMode && (
                <div className="flex items-center gap-2 px-1 py-1.5 mb-2 text-xs text-text-muted">
                  <GitCompareArrows className="w-3.5 h-3.5 text-accent-neon" />
                  Selecione 2 a 4 torneios para comparar · {selectedCompare.size} selecionado{selectedCompare.size !== 1 ? 's' : ''}
                </div>
              )}
              {groupByMonth(items).map(({ key, label, items: monthItems }) => (
                <div key={key} className="mb-6">
                  <div className="flex items-center gap-3 mb-3">
                    <h2 className="text-sm font-bold text-text-primary">{label}</h2>
                    <div className="flex-1 h-px bg-border-subtle" />
                    <span className="text-xs text-text-muted">{monthItems.length}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {monthItems.map((ed) => {
                      const isSelected = selectedCompare.has(ed.id);
                      return compareMode ? (
                        <div
                          key={ed.id}
                          className={`relative rounded-xl cursor-pointer transition-all ${
                            isSelected
                              ? 'ring-2 ring-accent-neon ring-offset-1 ring-offset-bg-base'
                              : selectedCompare.size >= 4 && !isSelected
                                ? 'opacity-50 cursor-not-allowed'
                                : ''
                          }`}
                          onClick={() => toggleCompareSelect(ed.id)}
                        >
                          <div className="absolute top-2 right-2 z-10">
                            {isSelected
                              ? <CheckSquare className="w-5 h-5 text-accent-neon drop-shadow" />
                              : <Square className="w-5 h-5 text-text-muted/60" />}
                          </div>
                          <TournamentCard edition={ed} variant="calendar" showEligibility={!!primaryProfileId} />
                        </div>
                      ) : (
                        <TournamentCard key={ed.id} edition={ed} variant="calendar" showEligibility={!!primaryProfileId} />
                      );
                    })}
                  </div>
                </div>
              ))}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 pt-4">
                  <button className="btn-secondary !py-2 !px-3 text-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</button>
                  <span className="text-xs text-text-muted">Página {page} de {totalPages}</span>
                  <button className="btn-secondary !py-2 !px-3 text-sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Próxima</button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ─── CALENDAR VIEW ─────────────────────────────────────────────────── */}
      {viewMode === 'calendar' && (
        <div className="space-y-3">
          {/* Month navigation */}
          <div className="flex items-center justify-between">
            <button
              className="btn-ghost !px-2"
              onClick={() => { setCalMonth(new Date(year, month - 1, 1)); setSelectedDate(null); }}
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <span className="font-semibold">{MONTHS_PT[month]} {year}</span>
            <button
              className="btn-ghost !px-2"
              onClick={() => { setCalMonth(new Date(year, month + 1, 1)); setSelectedDate(null); }}
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Weekday headers */}
          <div className="grid grid-cols-7 text-center">
            {WEEKDAYS_PT.map((d) => (
              <div key={d} className="text-[11px] font-bold text-text-muted py-1">{d}</div>
            ))}
          </div>

          {/* Calendar grid */}
          {loading ? (
            <div className="py-12 flex justify-center">
              <Loader2 className="w-7 h-7 text-accent-neon animate-spin" />
            </div>
          ) : (
            <>
              <div className="grid grid-cols-7 gap-y-1">
                {/* Empty cells before first day */}
                {Array.from({ length: firstDayOfMonth }).map((_, i) => (
                  <div key={`empty-${i}`} />
                ))}
                {/* Day cells */}
                {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => {
                  const key = dayKey(day);
                  const count = calendarMap[key]?.length ?? 0;
                  const hasItems = count > 0;
                  const isToday = key === TODAY;
                  const isSelected = key === selectedDate;
                  return (
                    <button
                      key={day}
                      onClick={() => setSelectedDate(isSelected ? null : key)}
                      className={`flex flex-col items-center py-1 rounded-xl transition-colors ${
                        isSelected
                          ? 'bg-accent-neon text-bg-base'
                          : isToday
                            ? 'border border-accent-neon text-accent-neon'
                            : hasItems
                              ? 'hover:bg-bg-elevated'
                              : 'hover:bg-bg-elevated opacity-50'
                      }`}
                    >
                      <span className={`text-sm font-${hasItems ? 'bold' : 'normal'}`}>{day}</span>
                      {/* Dot indicators for tournaments */}
                      <div className="flex gap-0.5 mt-0.5 h-1.5">
                        {hasItems && !isSelected && Array.from({ length: Math.min(count, 3) }).map((_, i) => (
                          <div key={i} className="w-1 h-1 rounded-full bg-accent-neon" />
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Legend */}
              {!selectedDate && (
                <div className="flex items-center gap-2 justify-center text-xs text-text-muted pt-1">
                  <div className="w-2 h-2 rounded-full bg-accent-neon" />
                  <span>Torneio neste dia</span>
                </div>
              )}

              {/* Selected day tournaments */}
              {selectedDate && (
                <div className="space-y-2 pt-1">
                  <div className="font-semibold text-sm">
                    {parseInt(selectedDate.slice(8), 10)} de {MONTHS_PT[parseInt(selectedDate.slice(5, 7), 10) - 1]}
                  </div>
                  {selectedDayItems.length === 0 ? (
                    <div className="card text-center py-6 text-sm text-text-muted">
                      Nenhum torneio começa neste dia.
                    </div>
                  ) : (
                    selectedDayItems.map((ed) => (
                      <TournamentCard key={ed.id} edition={ed} />
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ─── FLOATING COMPARE BAR ──────────────────────────────────────────── */}
      {compareMode && selectedCompare.size >= 2 && (
        <div className="fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-bg-card border border-accent-neon/40 shadow-xl rounded-2xl px-5 py-3">
          <GitCompareArrows className="w-4 h-4 text-accent-neon" />
          <span className="text-sm font-semibold text-accent-neon">{selectedCompare.size} selecionados</span>
          <button onClick={handleCompare} className="btn-primary !py-2 !px-4 text-sm">
            Comparar
          </button>
          <button onClick={toggleCompareMode} className="btn-ghost !p-1.5">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
