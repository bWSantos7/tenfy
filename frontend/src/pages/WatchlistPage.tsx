import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Loader2, Trash2, ExternalLink, CheckCircle, Clock, Trophy, User, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem, ParentChild } from '../types';
import { listWatchlist, deleteWatch, updateWatch, watchlistSummary, listChildren, listChildWatchlist } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const USER_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  none:                { label: 'Acompanhando', color: 'text-text-muted'      },
  intended:            { label: 'Pretendo ir',  color: 'text-accent-blue'     },
  registered_declared: { label: 'Inscrito',     color: 'text-status-open'     },
  withdrawn:           { label: 'Desistiu',     color: 'text-status-canceled' },
  completed:           { label: 'Concluído',    color: 'text-status-finished' },
};

interface ChildGroup {
  childName: string;
  childId: number;
  items: WatchlistItem[];
}

const TODAY = new Date().toISOString().slice(0, 10);

const MONTHS_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

function sortByDate(a: WatchlistItem, b: WatchlistItem): number {
  return (a.edition_detail.start_date || '').localeCompare(b.edition_detail.start_date || '');
}

function groupByMonth(list: WatchlistItem[]): { monthLabel: string; key: string; items: WatchlistItem[] }[] {
  const map = new Map<string, WatchlistItem[]>();
  list.forEach((item) => {
    const date = item.edition_detail.start_date || '';
    const key = date ? date.slice(0, 7) : 'sem-data';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(item);
  });
  const groups = Array.from(map.entries()).map(([key, items]) => {
    const [year, month] = key.split('-');
    const label = key === 'sem-data' ? 'Sem data definida' : `${MONTHS_PT[Number(month) - 1]} ${year}`;
    // Sort items within each group by start_date ascending (upcoming first)
    const sortedItems = [...items].sort(sortByDate);
    return { monthLabel: label, key, items: sortedItems };
  });
  // Sort groups chronologically; 'sem-data' always last
  return groups.sort((a, b) => {
    if (a.key === 'sem-data') return 1;
    if (b.key === 'sem-data') return -1;
    return a.key.localeCompare(b.key);
  });
}

function detectConflicts(items: WatchlistItem[]): Set<number> {
  const conflicting = new Set<number>();
  const active = items.filter((i) => i.edition_detail.start_date);
  for (let i = 0; i < active.length; i++) {
    for (let j = i + 1; j < active.length; j++) {
      const a = active[i].edition_detail;
      const b = active[j].edition_detail;
      const aStart = new Date(a.start_date!);
      const aEnd = a.end_date ? new Date(a.end_date) : aStart;
      const bStart = new Date(b.start_date!);
      const bEnd = b.end_date ? new Date(b.end_date) : bStart;
      if (aStart <= bEnd && bStart <= aEnd) {
        conflicting.add(active[i].id);
        conflicting.add(active[j].id);
      }
    }
  }
  return conflicting;
}

export const WatchlistPage: React.FC = () => {
  const { user } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [childGroups, setChildGroups] = useState<ChildGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<{ total: number; active_registrations: number; upcoming: number; past?: number } | null>(null);
  const [tab, setTab] = useState<'upcoming' | 'past'>('upcoming');
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [conflicts, setConflicts] = useState<Set<number>>(new Set());

  const isParent = user?.role === 'parent';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (isParent) {
        const [children, sm] = await Promise.all([
          listChildren().catch(() => [] as ParentChild[]),
          watchlistSummary().catch(() => null),
        ]);
        const childWatchlists = await Promise.all(
          children.map((link) => listChildWatchlist(link.child).catch(() => [] as WatchlistItem[])),
        );
        const groups: ChildGroup[] = children.map((link, i) => ({
          childName: link.child_detail.full_name || link.child_detail.email,
          childId: link.child,
          items: childWatchlists[i],
        }));
        const allItems = groups.flatMap((g) => g.items);
        setChildGroups(groups);
        setItems(allItems);
        setSummary(sm);
        setConflicts(detectConflicts(allItems));
      } else {
        const [data, sm] = await Promise.all([
          listWatchlist(),
          watchlistSummary().catch(() => null),
        ]);
        setChildGroups([]);
        setItems(data);
        setSummary(sm);
        setConflicts(detectConflicts(data));
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, [isParent]);

  useEffect(() => { load(); }, [load]);

  async function handleRemove(id: number) {
    try {
      await deleteWatch(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      setChildGroups((prev) => prev.map((g) => ({ ...g, items: g.items.filter((x) => x.id !== id) })));
      setConfirmRemove(null);
      toast.success('Removido da agenda');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  async function toggleRegistered(item: WatchlistItem) {
    const nextStatus = item.user_status === 'registered_declared' ? 'none' : 'registered_declared';
    try {
      await updateWatch(item.id, { user_status: nextStatus as WatchlistItem['user_status'] });
      const update = (list: WatchlistItem[]) =>
        list.map((x) => x.id === item.id ? { ...x, user_status: nextStatus as WatchlistItem['user_status'] } : x);
      setItems(update);
      setChildGroups((prev) => prev.map((g) => ({ ...g, items: update(g.items) })));
      toast.success(nextStatus === 'registered_declared' ? 'Marcado como inscrito!' : 'Status removido.');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  const now = TODAY;
  const upcoming = items.filter((i) => !i.edition_detail.end_date || i.edition_detail.end_date >= now).sort(sortByDate);
  const past     = items.filter((i) => i.edition_detail.end_date && i.edition_detail.end_date < now).sort(sortByDate);
  const displayed = tab === 'upcoming' ? upcoming : past;
  const displayedGroups = groupByMonth(displayed);

  function renderGrouped(itemsToRender: WatchlistItem[]) {
    if (!isParent || childGroups.length === 0) {
      return itemsToRender.map(renderItem);
    }
    const ids = new Set(itemsToRender.map((i) => i.id));
    return childGroups.flatMap((group) => {
      const filtered = group.items.filter((i) => ids.has(i.id));
      if (filtered.length === 0) return [];
      return [
        <div key={`header-${group.childId}`} className="flex items-center gap-1.5 px-1 mt-3 mb-1">
          <User className="w-3.5 h-3.5 text-accent-blue shrink-0" />
          <span className="text-xs font-bold text-accent-blue">{group.childName}</span>
        </div>,
        ...filtered.map(renderItem),
      ];
    });
  }

  function renderItem(item: WatchlistItem) {
    const statusInfo = USER_STATUS_LABELS[item.user_status] ?? USER_STATUS_LABELS.none;
    const isRegistered = item.user_status === 'registered_declared';
    return (
      <div key={item.id} className="relative">
        {conflicts.has(item.id) && (
          <div className="flex items-center gap-1.5 px-1 mb-1 mt-2">
            <AlertTriangle className="w-3 h-3 text-status-closing" />
            <span className="text-[10px] text-status-closing font-medium">Conflito de datas</span>
          </div>
        )}
        <TournamentCard edition={item.edition_detail} />

        {/* Status + actions bar */}
        <div className="flex items-center justify-between mt-1.5 px-1">
          <span className={`text-xs font-semibold ${statusInfo.color}`}>
            {statusInfo.label}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => toggleRegistered(item)}
              className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${
                isRegistered
                  ? 'bg-status-open/15 border-status-open/40 text-status-open'
                  : 'bg-bg-card border-border-subtle text-text-muted hover:text-accent-neon hover:border-accent-neon/40'
              }`}
              title={isRegistered ? 'Remover declaração de inscrição' : 'Declarar que você está inscrito neste torneio (informativo, não validado pela fonte oficial)'}
            >
              <CheckCircle className="w-3.5 h-3.5" />
              {isRegistered ? 'Inscrito (declarado)' : 'Declarar inscrição'}
            </button>

            {confirmRemove === item.id ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleRemove(item.id)}
                  className="text-xs px-2 py-1 rounded-lg bg-red-500/15 border border-red-500/40 text-red-400 hover:bg-red-500/25"
                >Confirmar</button>
                <button onClick={() => setConfirmRemove(null)} className="text-xs px-2 py-1 rounded-lg bg-bg-elevated text-text-muted hover:text-text-primary">Cancelar</button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmRemove(item.id)}
                className="p-1.5 rounded-lg bg-bg-elevated hover:bg-bg-card text-text-muted hover:text-red-400 transition-colors"
                title="Remover da agenda"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Minha agenda</h1>
          <p className="text-sm text-text-muted">Torneios que você está acompanhando</p>
        </div>
      </div>

      {/* Summary cards */}
      {summary && summary.total > 0 && (
        <div className="grid grid-cols-4 gap-2">
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-accent-neon">{summary.total}</div>
            <div className="text-[10px] text-text-muted">Total</div>
          </div>
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-accent-blue">{summary.upcoming}</div>
            <div className="text-[10px] text-text-muted">Próximos</div>
          </div>
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-text-muted">{summary.past ?? past.length}</div>
            <div className="text-[10px] text-text-muted">Passados</div>
          </div>
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-status-open">{summary.active_registrations}</div>
            <div className="text-[10px] text-text-muted">Inscrições</div>
          </div>
        </div>
      )}

      {/* Conflitos */}
      {conflicts.size > 0 && (
        <div className="flex items-center gap-2 bg-status-closing/10 border border-status-closing/30 rounded-xl px-3 py-2.5">
          <AlertTriangle className="w-4 h-4 text-status-closing shrink-0" />
          <span className="text-xs text-status-closing">
            {conflicts.size} torneio{conflicts.size > 1 ? 's' : ''} com datas sobrepostas na sua agenda.
          </span>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card text-center py-10 space-y-3">
          <Star className="w-10 h-10 text-text-muted mx-auto" />
          <p className="font-semibold">Nenhum torneio na agenda</p>
          <p className="text-sm text-text-secondary">
            {isParent ? 'Nenhum dependente tem torneios na agenda ainda.' : 'Você ainda não está acompanhando nenhum torneio.'}
          </p>
          {!isParent && (
            <Link to="/torneios" className="btn-primary inline-flex items-center gap-2 !text-sm">
              Explorar torneios <ExternalLink className="w-4 h-4" />
            </Link>
          )}
        </div>
      ) : (
        <>
          {/* Tabs próximos / passados */}
          <div className="flex gap-1 bg-bg-card border border-border-subtle rounded-xl p-1">
            <button
              onClick={() => setTab('upcoming')}
              className={`flex-1 py-1.5 rounded-lg text-sm font-semibold transition-colors ${tab === 'upcoming' ? 'bg-accent-neon' : 'text-text-muted hover:text-text-primary'}`}
              style={tab === 'upcoming' ? { color: 'rgb(var(--btn-text))' } : undefined}
            >
              <Clock className="w-3.5 h-3.5 inline mr-1" />
              Próximos ({upcoming.length})
            </button>
            <button
              onClick={() => setTab('past')}
              className={`flex-1 py-1.5 rounded-lg text-sm font-semibold transition-colors ${tab === 'past' ? 'bg-accent-neon' : 'text-text-muted hover:text-text-primary'}`}
              style={tab === 'past' ? { color: 'rgb(var(--btn-text))' } : undefined}
            >
              <Trophy className="w-3.5 h-3.5 inline mr-1" />
              Passados ({past.length})
            </button>
          </div>

          {displayed.length === 0 ? (
            <div className="card text-center py-8 text-text-muted text-sm">
              {tab === 'upcoming' ? 'Nenhum torneio próximo na agenda.' : 'Nenhum torneio passado na agenda.'}
            </div>
          ) : (
            <div className="space-y-1">
              {displayedGroups.map((group) => (
                <div key={group.key}>
                  <div className="flex items-center gap-2 px-1 pt-3 pb-1.5">
                    <span className="text-xs font-bold text-text-muted uppercase tracking-wide">{group.monthLabel}</span>
                    <div className="flex-1 h-px bg-border-subtle" />
                    <span className="text-xs text-text-muted">{group.items.length}</span>
                  </div>
                  <div className="space-y-3">
                    {renderGrouped(group.items)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};
