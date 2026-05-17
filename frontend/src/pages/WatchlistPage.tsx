import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Star, Loader2, Trash2, ExternalLink, CheckCircle, Clock, Trophy } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem } from '../types';
import { listWatchlist, deleteWatch, updateWatch, watchlistSummary } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtDateRange } from '../utils/format';

const USER_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  none:                 { label: 'Acompanhando',  color: 'text-text-muted' },
  intended:             { label: 'Pretendo ir',   color: 'text-accent-blue' },
  registered_declared:  { label: 'Inscrito',      color: 'text-status-open' },
  withdrawn:            { label: 'Desistiu',      color: 'text-status-canceled' },
  completed:            { label: 'Concluído',     color: 'text-status-finished' },
};

export const WatchlistPage: React.FC = () => {
  const { user } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<{ total: number; active_registrations: number; upcoming: number } | null>(null);
  const [tab, setTab] = useState<'upcoming' | 'past'>('upcoming');
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, sum] = await Promise.all([
        listWatchlist(),
        watchlistSummary().catch(() => null),
      ]);
      setItems(data);
      setSummary(sum);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleRemove(id: number) {
    try {
      await deleteWatch(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
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
      setItems((prev) => prev.map((x) => x.id === item.id ? { ...x, user_status: nextStatus as WatchlistItem['user_status'] } : x));
      toast.success(nextStatus === 'registered_declared' ? 'Marcado como inscrito!' : 'Status removido.');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  // Separar upcoming vs past baseado na data do torneio
  const now = new Date().toISOString().slice(0, 10);
  const upcoming = items.filter((i) => !i.edition_detail.end_date || i.edition_detail.end_date >= now);
  const past     = items.filter((i) => i.edition_detail.end_date && i.edition_detail.end_date < now);
  const displayed = tab === 'upcoming' ? upcoming : past;

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
        <div className="grid grid-cols-3 gap-2">
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-accent-neon">{summary.total}</div>
            <div className="text-[11px] text-text-muted">Total</div>
          </div>
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-status-open">{summary.active_registrations}</div>
            <div className="text-[11px] text-text-muted">Inscritos</div>
          </div>
          <div className="card !p-3 text-center">
            <div className="text-xl font-bold text-accent-blue">{summary.upcoming}</div>
            <div className="text-[11px] text-text-muted">Próximos</div>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card text-center py-10 space-y-3">
          <Star className="w-10 h-10 text-text-muted mx-auto" />
          <p className="font-semibold">Nenhum torneio na agenda</p>
          <p className="text-sm text-text-secondary">Você ainda não está acompanhando nenhum torneio.</p>
          <Link to="/torneios" className="btn-primary inline-flex items-center gap-2 !text-sm">
            Explorar torneios <ExternalLink className="w-4 h-4" />
          </Link>
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
            <div className="space-y-3">
              {displayed.map((item) => {
                const statusInfo = USER_STATUS_LABELS[item.user_status] ?? USER_STATUS_LABELS.none;
                const isRegistered = item.user_status === 'registered_declared';
                return (
                  <div key={item.id} className="relative">
                    <TournamentCard edition={item.edition_detail} />

                    {/* Status + actions bar */}
                    <div className="flex items-center justify-between mt-1.5 px-1">
                      <span className={`text-xs font-semibold ${statusInfo.color}`}>
                        {statusInfo.label}
                      </span>
                      <div className="flex items-center gap-1">
                        {/* Marcar como inscrito — igual ao mobile */}
                        <button
                          onClick={() => toggleRegistered(item)}
                          className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${
                            isRegistered
                              ? 'bg-status-open/15 border-status-open/40 text-status-open'
                              : 'bg-bg-card border-border-subtle text-text-muted hover:text-accent-neon hover:border-accent-neon/40'
                          }`}
                          title={isRegistered ? 'Remover status de inscrito' : 'Marcar como inscrito'}
                        >
                          <CheckCircle className="w-3.5 h-3.5" />
                          {isRegistered ? 'Inscrito' : 'Marcar inscrito'}
                        </button>

                        {/* Remover */}
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
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};
