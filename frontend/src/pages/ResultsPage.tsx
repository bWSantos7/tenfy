import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, RefreshCw, LinkIcon, User } from 'lucide-react';
import toast from 'react-hot-toast';
import { ParentChild, PlayerProfile, TiData, TiResultEntry } from '../types';
import { fetchTiData, listChildProfiles, listChildren, listProfiles, syncTiData } from '../services/data';
import { useAuth } from '../contexts/AuthContext';

// ── helpers ──────────────────────────────────────────────────────────────────

interface TournamentGroup {
  key: string;
  tournament: string;
  date: string;
  federation: string;
  matches: TiResultEntry[];
}

function groupByTournament(results: TiResultEntry[]): TournamentGroup[] {
  const groups: TournamentGroup[] = [];
  const index: Record<string, number> = {};
  for (const r of results) {
    const key = `${r.tournament}||${r.date}`;
    if (key in index) {
      groups[index[key]].matches.push(r);
    } else {
      index[key] = groups.length;
      groups.push({ key, tournament: r.tournament ?? '', date: r.date ?? '', federation: r.federation ?? '', matches: [r] });
    }
  }
  return groups;
}

// ── component ─────────────────────────────────────────────────────────────────

export const ResultsPage: React.FC = () => {
  const { user } = useAuth();
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(true);
  const [tiSyncing, setTiSyncing] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);
  const [children, setChildren] = useState<ParentChild[]>([]);
  const [selectedChildId, setSelectedChildId] = useState<number | null>(null);

  const isParent = user?.role === 'parent';

  // Load profiles (own) or children list (parent)
  useEffect(() => {
    if (isParent) {
      listChildren()
        .then((data) => {
          setChildren(data);
          setSelectedChildId((prev) => prev ?? (data[0]?.child ?? null));
        })
        .catch(() => setTiLoading(false));
    } else {
      listProfiles()
        .then((profs: PlayerProfile[]) => {
          const primary = profs.find((p) => p.is_primary) ?? profs[0];
          if (primary) setPrimaryProfileId(primary.id);
          else setTiLoading(false);
        })
        .catch(() => setTiLoading(false));
    }
  }, [isParent]);

  // When a child is selected (parent), load that child's primary profile
  useEffect(() => {
    if (!isParent || !selectedChildId) return;
    setTiLoading(true);
    setTiData(null);
    listChildProfiles(selectedChildId)
      .then((profs) => {
        const primary = profs.find((p) => p.is_primary) ?? profs[0];
        if (primary) setPrimaryProfileId(primary.id);
        else { setPrimaryProfileId(null); setTiLoading(false); }
      })
      .catch(() => setTiLoading(false));
  }, [isParent, selectedChildId]);

  useEffect(() => {
    if (!primaryProfileId) return;
    setTiLoading(true);
    fetchTiData(primaryProfileId)
      .then((d) => setTiData(d))
      .catch(() => {})
      .finally(() => setTiLoading(false));
  }, [primaryProfileId]);

  async function handleTiSync() {
    if (!primaryProfileId) return;
    setTiSyncing(true);
    try {
      await syncTiData(primaryProfileId);
      const fresh = await fetchTiData(primaryProfileId);
      setTiData(fresh);
      toast.success('Dados atualizados com sucesso.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Não foi possível atualizar agora.');
    } finally {
      setTiSyncing(false);
    }
  }

  const groups   = groupByTournament(tiData?.results ?? []);
  const wins     = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W').length ?? 0;
  const losses   = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('D')).length ?? 0;
  const total    = tiData?.results.length ?? 0;

  return (
    <div className="space-y-4 pb-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Resultados</h1>
          <p className="text-sm text-text-muted">Jogos importados automaticamente pelo Tênis Integrado</p>
        </div>
        {tiData?.ti_id && (
          <button
            onClick={handleTiSync}
            disabled={tiSyncing}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-accent-neon transition-colors disabled:opacity-50 mt-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${tiSyncing ? 'animate-spin' : ''}`} />
            {tiSyncing ? 'Atualizando...' : 'Atualizar'}
          </button>
        )}
      </div>

      {/* ── Seletor de dependente (pai com 1 ou mais filhos) ── */}
      {isParent && children.length >= 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
          {children.map((c) => {
            const isActive = c.child === selectedChildId;
            return (
              <button
                key={c.id}
                onClick={() => setSelectedChildId(c.child)}
                className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-colors ${
                  isActive
                    ? 'bg-accent-neon text-bg-base border-accent-neon'
                    : 'bg-bg-card border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent-neon/50'
                }`}
              >
                <User className="w-3 h-3 shrink-0" />
                <span className="truncate max-w-[120px]">{c.child_detail.full_name || '—'}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Stats */}
      {tiData?.has_ti_id && total > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'Jogos',    value: total,  color: 'text-accent-blue'     },
            { label: 'Vitórias', value: wins,   color: 'text-status-open'     },
            { label: 'Derrotas', value: losses, color: 'text-status-canceled' },
          ].map((s) => (
            <div key={s.label} className="card text-center !py-3">
              <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-[10px] text-text-muted mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      {tiLoading ? (
        <div className="card flex items-center justify-center py-12">
          <Loader2 className="w-7 h-7 text-accent-neon animate-spin" />
        </div>

      ) : !tiData?.has_ti_id ? (
        <div className="card flex items-start gap-3 py-6">
          <LinkIcon className="w-5 h-5 text-text-muted shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium">ID do Tênis Integrado não vinculado</p>
            <p className="text-xs text-text-muted mt-0.5">
              Para importar jogos automaticamente, vincule seu ID no{' '}
              <Link to="/perfil" className="text-accent-blue hover:underline">Perfil</Link>.
            </p>
          </div>
        </div>

      ) : groups.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-sm font-medium mb-1">Nenhum jogo encontrado</p>
          <p className="text-xs text-text-muted">Nenhum resultado foi encontrado no Tênis Integrado para este perfil.</p>
        </div>

      ) : (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.key} className="card !p-0 overflow-hidden">
              {/* Tournament header */}
              <div className="px-4 py-3 border-b border-border-subtle bg-bg-elevated/60">
                <p className="font-semibold text-sm leading-snug">{g.tournament}</p>
                {g.date && <p className="text-[11px] text-text-muted mt-0.5">{g.date}</p>}
                {g.federation && (
                  <span className="inline-block mt-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full bg-accent-blue/15 text-accent-blue">
                    {g.federation}
                  </span>
                )}
              </div>

              {/* Match rows */}
              <div className="divide-y divide-border-subtle">
                {g.matches.map((m, i) => {
                  const isWin = m.outcome?.toUpperCase().startsWith('V') || m.outcome?.toUpperCase() === 'W';
                  return (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                      {/* Phase */}
                      <span className="w-8 text-[11px] font-mono text-text-muted shrink-0">{m.round ?? '—'}</span>

                      {/* Opponent */}
                      <span className="flex-1 text-xs text-text-secondary truncate">{m.opponent ?? '—'}</span>

                      {/* Outcome + score */}
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${isWin ? 'bg-status-open/15 text-status-open' : 'bg-status-canceled/15 text-status-canceled'}`}>
                          {m.outcome ? m.outcome.slice(0, 1).toUpperCase() : '?'}
                        </span>
                        {m.score && (
                          <span className="text-[11px] text-text-muted font-mono">{m.score}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {tiData?.is_stale && (
            <p className="text-[10px] text-text-muted text-center pt-1">
              Dados podem estar desatualizados. Clique em Atualizar.
            </p>
          )}
        </div>
      )}
    </div>
  );
};
