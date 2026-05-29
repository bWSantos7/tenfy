import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, RefreshCw, LinkIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { PlayerProfile, TiData } from '../types';
import { fetchTiData, listProfiles, syncTiData } from '../services/data';
import { useAuth } from '../contexts/AuthContext';

export const ResultsPage: React.FC = () => {
  const { user } = useAuth();
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(true);
  const [tiSyncing, setTiSyncing] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);

  useEffect(() => {
    listProfiles()
      .then((profs: PlayerProfile[]) => {
        const primary = profs.find((p) => p.is_primary) ?? profs[0];
        if (primary) setPrimaryProfileId(primary.id);
      })
      .catch(() => {})
      .finally(() => setTiLoading(false));
  }, []);

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

  const wins   = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W').length ?? 0;
  const losses = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('D')).length ?? 0;
  const total  = (tiData?.results.length ?? 0);

  return (
    <div className="space-y-4 pb-4">
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

      {/* Stats do TI */}
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

      {/* Conteúdo TI */}
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
      ) : tiData.results.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-sm font-medium mb-1">Nenhum jogo encontrado</p>
          <p className="text-xs text-text-muted">Nenhum resultado foi encontrado no Tênis Integrado para este perfil.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {tiData.results.map((r, i) => {
            const isWin = r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W';
            return (
              <div key={i} className="card flex items-center gap-3">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 text-sm font-bold ${isWin ? 'bg-status-open/15 text-status-open' : 'bg-status-canceled/15 text-status-canceled'}`}>
                  {r.outcome ? r.outcome.slice(0, 1).toUpperCase() : '?'}
                </div>
                <div className="flex-1 min-w-0">
                  {r.tournament && <p className="text-sm font-semibold truncate">{r.tournament}</p>}
                  {r.opponent && <p className="text-xs text-text-muted">vs {r.opponent}</p>}
                  <div className="flex items-center gap-2 text-[10px] text-text-muted mt-0.5 flex-wrap">
                    {r.round    && <span>{r.round}</span>}
                    {r.category && <span>• {r.category}</span>}
                    {r.score    && <span>• {r.score}</span>}
                    {r.date     && <span>• {r.date}</span>}
                  </div>
                </div>
              </div>
            );
          })}
          {tiData.is_stale && (
            <p className="text-[10px] text-text-muted text-center pt-1">
              Dados podem estar desatualizados. Clique em Atualizar.
            </p>
          )}
        </div>
      )}
    </div>
  );
};
