import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, Loader2, X, MapPin, List, Calendar, ChevronLeft, ChevronRight, GitCompareArrows, CheckSquare, Square } from 'lucide-react';
import { TournamentEditionList } from '../types';
import {
  listEditions,
  listOrganizations,
  calendar as calendarApi,
  TournamentFilters,
  OrganizationOption,
} from '../services/tournaments';
import { listProfiles } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
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
  { v: 'announced', l: 'Anunciados' },
  { v: 'in_progress', l: 'Em andamento' },
  { v: 'draws_published', l: 'Chaves publicadas' },
  { v: 'finished', l: 'Finalizados' },
  { v: 'canceled', l: 'Cancelados' },
];

const MONTHS_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const WEEKDAYS_PT = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
const TODAY = new Date().toISOString().slice(0, 10);

const STATUS_SORT_PRIORITY: Record<string, number> = {
  open: 0,
  closing_soon: 0,
  announced: 1,
  in_progress: 1,
  draws_published: 1,
  closed: 2,
  finished: 3,
  canceled: 4,
  unknown: 5,
};

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
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    listProfiles().then((profiles) => {
      const list = Array.isArray(profiles) ? profiles : (profiles as any).results ?? [];
      let primary = null;
      if (user?.role === 'parent' && user.id) {
        const activeId = getActiveProfileId(user.id);
        if (activeId) primary = list.find((p: any) => p.id === activeId) ?? null;
      }
      if (!primary) primary = pickBestProfile(list);
      if (primary) {
        setPrimaryProfileId(primary.id);
        // On the very first visit (no filters saved in sessionStorage), pre-apply
        // the profile's modality so the user sees only their sport by default.
        // They can manually clear the modality filter to browse all modalities.
        if (primary.preferred_modality && saved.current === null) {
          setFilters((f) => ({ ...f, modality: primary.preferred_modality }));
        }
      }
    }).catch(() => {});
    listOrganizations().then(setOrganizations).catch(() => setOrganizations([]));
  }, [user?.id, user?.role]);

  // Auto-apply text search after 400ms debounce
  useEffect(() => {
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      setFilters((f) => ({ ...f, q: q.trim() || undefined }));
      setPage(1);
    }, 400);
    return () => { if (searchDebounce.current) clearTimeout(searchDebounce.current); };
  }, [q]);

  const hasAnyFilter = useMemo(
    () => !!(
      filters.status || filters.state || filters.q || filters.modality
      || filters.surface || filters.from_date || filters.to_date
      || filters.organization || filters.category
    ),
    [filters],
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
    const nearFilter = nearMe && primaryProfileId ? { near_profile: primaryProfileId } : {};
    listEditions({ ...filters, ...nearFilter, page, page_size: 20, ordering: 'status_priority,start_date' })
      .then((data) => {
        if (cancel) return;
        setItems(sortTournaments(data.results));
        setTotalPages(data.total_pages || 1);
      })
      .catch(() => setItems([]))
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [filters, page, nearMe, primaryProfileId, viewMode]);

  // Load calendar view
  useEffect(() => {
    if (viewMode !== 'calendar') return;
    let cancel = false;
    setLoading(true);
    const nearFilter = nearMe && primaryProfileId ? { near_profile: primaryProfileId } : {};
    calendarApi({ ...filters, ...nearFilter })
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
  }, [filters, nearMe, primaryProfileId, viewMode]);

  function applySearch() {
    setPage(1);
    setFilters((f) => ({ ...f, q: q.trim() || undefined }));
  }

  function clearFilters() {
    setQ('');
    setFilters({ status: '', state: '' });
    setNearMe(false);
    setPage(1);
    try { sessionStorage.removeItem(FILTER_SESSION_KEY); } catch {}
  }

  function switchMode(mode: ViewMode) {
    setViewMode(mode);
    setSelectedDate(null);
    setPage(1);
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
          />
        </div>
        <button
          className="btn-secondary !px-3 relative"
          onClick={() => setShowFilters((v) => !v)}
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
            <div>
              <label className="text-xs text-text-secondary mb-1 block">UF</label>
              <select
                className="input-base"
                value={filters.state || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, state: e.target.value })); }}
              >
                {STATES.map((s) => (
                  <option key={s} value={s}>{s || 'Todos'}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Status</label>
              <select
                className="input-base"
                value={filters.status || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, status: e.target.value })); }}
              >
                {STATUS_OPTS.map((o) => (
                  <option key={o.v} value={o.v}>{o.l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Modalidade</label>
              <select
                className="input-base"
                value={filters.modality || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, modality: e.target.value })); }}
              >
                <option value="">Todas</option>
                <option value="tennis">Tênis</option>
                <option value="beach_tennis">Beach Tennis</option>
                <option value="wheelchair">Cadeira de rodas</option>
                <option value="padel">Padel</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Superfície</label>
              <select
                className="input-base"
                value={filters.surface || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, surface: e.target.value })); }}
              >
                <option value="">Todas</option>
                <option value="clay">Saibro</option>
                <option value="hard">Rápida</option>
                <option value="grass">Grama</option>
                <option value="sand">Areia</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Data inicial</label>
              <input
                type="date"
                className="input-base"
                value={filters.from_date || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, from_date: e.target.value || undefined })); }}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Data final</label>
              <input
                type="date"
                className="input-base"
                value={filters.to_date || ''}
                onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, to_date: e.target.value || undefined })); }}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Entidade / fonte</label>
              <select
                className="input-base"
                value={filters.organization ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setPage(1);
                  setFilters((f) => ({ ...f, organization: v ? Number(v) : undefined }));
                }}
              >
                <option value="">Todas</option>
                {organizations.map((o) => (
                  <option key={o.id} value={o.id}>{o.short_name || o.name}</option>
                ))}
              </select>
            </div>
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
            <div className="space-y-3">
              {compareMode && (
                <div className="flex items-center gap-2 px-1 py-1.5 text-xs text-text-muted">
                  <GitCompareArrows className="w-3.5 h-3.5 text-accent-neon" />
                  Selecione 2 a 4 torneios para comparar · {selectedCompare.size} selecionado{selectedCompare.size !== 1 ? 's' : ''}
                </div>
              )}
              {items.map((ed, i) => {
                const dynStatus = ed.dynamic_status ?? ed.status ?? 'unknown';
                const group = getStatusGroup(dynStatus);
                const prevGroup = i > 0
                  ? getStatusGroup(items[i - 1].dynamic_status ?? items[i - 1].status ?? 'unknown')
                  : null;
                const showHeader = !filters.status && group !== prevGroup;
                const isSelected = selectedCompare.has(ed.id);
                return (
                  <React.Fragment key={ed.id}>
                    {showHeader && (
                      <div className={`text-[11px] font-bold text-text-muted uppercase tracking-wider px-1 ${i > 0 ? 'pt-3 pb-0.5' : 'pb-0.5'}`}>
                        {GROUP_LABELS[group] ?? group}
                      </div>
                    )}
                    {compareMode ? (
                      <div
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
                        <TournamentCard edition={ed} />
                      </div>
                    ) : (
                      <TournamentCard edition={ed} />
                    )}
                  </React.Fragment>
                );
              })}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 pt-4">
                  <button
                    className="btn-secondary !py-2 !px-3 text-sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Anterior
                  </button>
                  <span className="text-xs text-text-muted">Página {page} de {totalPages}</span>
                  <button
                    className="btn-secondary !py-2 !px-3 text-sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Próxima
                  </button>
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
