import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Award, Trophy, Loader2, Plus, Check, X, Edit2, User, AlertCircle, PenLine, RefreshCw, LinkIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem, PlayerProfile, ParentChild, TiData } from '../types';
import { fetchTiData, listWatchlist, saveResult, listProfiles, listChildren, listChildWatchlist, listChildProfiles, syncTiData } from '../services/data';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtDateRange } from '../utils/format';

const CATEGORY_OPTIONS = [
  { value: '',       label: 'Não informada'  },
  { value: '10',     label: '10 anos'        },
  { value: '12',     label: '12 anos'        },
  { value: '14',     label: '14 anos'        },
  { value: '16',     label: '16 anos'        },
  { value: '18',     label: '18 anos'        },
  { value: 'junior', label: 'Juvenil'        },
  { value: 'adulto', label: 'Adulto'         },
  { value: '40',     label: 'Masters 40+'    },
  { value: '50',     label: 'Masters 50+'    },
];

interface ResultForm {
  category_played: string;
  position: string;
  wins: string;
  losses: string;
  notes: string;
}

const emptyForm = (): ResultForm => ({
  category_played: '',
  position: '',
  wins: '0',
  losses: '0',
  notes: '',
});

export const ResultsPage: React.FC = () => {
  const { user } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [profileNames, setProfileNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState<ResultForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(false);
  const [tiSyncing, setTiSyncing] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      if (user?.role === 'parent') {
        const [ownData, children, ownProfs] = await Promise.all([
          listWatchlist().catch(() => [] as WatchlistItem[]),
          listChildren().catch(() => [] as ParentChild[]),
          listProfiles().catch(() => [] as PlayerProfile[]),
        ]);
        const childWatchlists = await Promise.all(
          children.map((c) => listChildWatchlist(c.child).catch(() => [] as WatchlistItem[])),
        );
        const childProfileArrays = await Promise.all(
          children.map((c) => listChildProfiles(c.child).catch(() => [] as PlayerProfile[])),
        );
        const ownItems = ownData.filter((it) => it.user_status === 'registered_declared' || !!it.result);
        const childItems = children.flatMap((_, i) =>
          childWatchlists[i].filter((it) => it.user_status === 'registered_declared' || !!it.result),
        );
        const nameMap: Record<number, string> = {};
        ownProfs.forEach((p) => { nameMap[p.id] = p.display_name; });
        children.forEach((link, i) => {
          childProfileArrays[i].forEach((p) => {
            nameMap[p.id] = `${link.child_detail.full_name || link.child_detail.email} — ${p.display_name}`;
          });
        });
        setItems([...ownItems, ...childItems]);
        setProfileNames(nameMap);
      } else {
        const [data, profs] = await Promise.all([
          listWatchlist(),
          listProfiles().catch(() => [] as PlayerProfile[]),
        ]);
        const primary = profs.find((p) => p.is_primary) ?? profs[0];
        if (primary) setPrimaryProfileId(primary.id);
        setItems(data.filter((i) => i.user_status === 'registered_declared' || !!i.result));
        setProfileNames(Object.fromEntries(profs.map((p) => [p.id, p.display_name])));
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!primaryProfileId || user?.role === 'parent') return;
    setTiLoading(true);
    fetchTiData(primaryProfileId).then((d) => setTiData(d)).catch(() => {}).finally(() => setTiLoading(false));
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

  function startEdit(item: WatchlistItem) {
    setEditing(item.id);
    setForm({
      category_played: item.result?.category_played ?? '',
      position: item.result?.position?.toString() ?? '',
      wins: item.result?.wins?.toString() ?? '0',
      losses: item.result?.losses?.toString() ?? '0',
      notes: item.result?.notes ?? '',
    });
  }

  async function handleSave(itemId: number) {
    setSaving(true);
    try {
      await saveResult(itemId, {
        category_played: form.category_played || undefined,
        position: form.position ? Number(form.position) : null,
        wins: Number(form.wins),
        losses: Number(form.losses),
        notes: form.notes,
      });
      toast.success('Resultado salvo!');
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSaving(false);
    }
  }

  const totalWins    = items.reduce((s, i) => s + (i.result?.wins   ?? 0), 0);
  const totalLosses  = items.reduce((s, i) => s + (i.result?.losses ?? 0), 0);
  const totalMatches = totalWins + totalLosses;
  const positions    = items.map((i) => i.result?.position).filter((p): p is number => p != null);
  const bestPosition = positions.length > 0 ? Math.min(...positions) : null;

  // Group by profile for parent users
  function renderGrouped() {
    if (user?.role !== 'parent') return items.map(renderItem);

    const groups: Record<string, WatchlistItem[]> = {};
    items.forEach((item) => {
      const key = item.profile != null ? String(item.profile) : 'none';
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });

    return Object.entries(groups).flatMap(([key, groupItems]) => {
      const profileId = key === 'none' ? null : Number(key);
      const name = profileId ? (profileNames[profileId] ?? 'Dependente') : 'Sem perfil';
      return [
        <div key={`hd-${key}`} className="flex items-center gap-1.5 px-1 mt-3 mb-1">
          <User className="w-3.5 h-3.5 text-accent-blue shrink-0" />
          <span className="text-xs font-bold text-accent-blue">{name}</span>
        </div>,
        ...groupItems.map(renderItem),
      ];
    });
  }

  function renderItem(item: WatchlistItem) {
    return (
      <div key={item.id} className="card space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <Link
              to={`/torneios/${item.edition}`}
              className="font-semibold text-sm hover:text-accent-neon transition-colors line-clamp-1"
            >
              {item.edition_detail.title}
            </Link>
            <div className="text-xs text-text-muted mt-0.5">
              {fmtDateRange(item.edition_detail.start_date, item.edition_detail.end_date)}
              {item.edition_detail.venue_city && ` • ${item.edition_detail.venue_city}/${item.edition_detail.venue_state}`}
            </div>
          </div>
          {item.result?.position === 1 && <Trophy className="w-5 h-5 text-status-closing shrink-0" />}
        </div>

        {editing === item.id ? (
          <div className="space-y-3 border-t border-border-subtle pt-3">
            {/* Vitórias / Derrotas / Posição */}
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="text-xs text-text-muted mb-1 block">Vitórias</label>
                <input type="number" min={0} className="input-base !py-2 text-sm"
                  value={form.wins} onChange={(e) => setForm((f) => ({ ...f, wins: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Derrotas</label>
                <input type="number" min={0} className="input-base !py-2 text-sm"
                  value={form.losses} onChange={(e) => setForm((f) => ({ ...f, losses: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Posição</label>
                <input type="number" min={1} className="input-base !py-2 text-sm" placeholder="—"
                  value={form.position} onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))} />
              </div>
            </div>

            {/* Categoria */}
            <div>
              <label className="text-xs text-text-muted mb-1 block">Categoria disputada</label>
              <select className="input-base !py-2 text-sm" value={form.category_played}
                onChange={(e) => setForm((f) => ({ ...f, category_played: e.target.value }))}>
                {CATEGORY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            {/* Notas */}
            <div>
              <label className="text-xs text-text-muted mb-1 block">Notas / observações</label>
              <textarea rows={2} className="input-base text-sm resize-none"
                placeholder="Descreva como foi a competição..."
                value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
            </div>

            <div className="flex gap-2">
              <button className="btn-secondary !py-2 flex-1 flex items-center justify-center gap-1 text-sm"
                onClick={() => setEditing(null)}>
                <X className="w-3.5 h-3.5" /> Cancelar
              </button>
              <button className="btn-primary !py-2 flex-1 flex items-center justify-center gap-1 text-sm"
                onClick={() => handleSave(item.id)} disabled={saving}>
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                Salvar
              </button>
            </div>
          </div>
        ) : item.result ? (
          <div className="border-t border-border-subtle pt-3 space-y-2">
            {/* Stats */}
            <div className="grid grid-cols-3 gap-2">
              {item.result.position != null && (
                <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
                  <div className="text-[10px] text-text-muted mb-0.5">Posição</div>
                  <div className="font-bold text-base text-accent-neon">
                    {item.result.position === 1 ? '🥇' : item.result.position === 2 ? '🥈' : item.result.position === 3 ? '🥉' : `#${item.result.position}`}
                  </div>
                </div>
              )}
              <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
                <div className="text-[10px] text-text-muted mb-0.5">V / D</div>
                <div className="font-bold text-base">
                  <span className="text-status-open">{item.result.wins ?? 0}</span>
                  <span className="text-text-muted mx-1">/</span>
                  <span className="text-status-canceled">{item.result.losses ?? 0}</span>
                </div>
              </div>
              {item.result.category_played && (
                <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
                  <div className="text-[10px] text-text-muted mb-0.5">Categoria</div>
                  <div className="font-bold text-xs line-clamp-2">{item.result.category_played}</div>
                </div>
              )}
            </div>
            {item.result.notes && (
              <p className="text-xs text-text-muted italic">"{item.result.notes}"</p>
            )}
            <div className="flex items-center justify-between gap-2 pt-1">
              <span className="flex items-center gap-1 text-[10px] text-text-muted px-2 py-0.5 rounded-md bg-bg-elevated border border-border-subtle">
                <PenLine className="w-2.5 h-2.5" /> Inserido manualmente
              </span>
              <button onClick={() => startEdit(item)}
                className="flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-text-muted hover:text-accent-neon border border-dashed border-border-subtle rounded-xl transition-colors">
                <Edit2 className="w-3 h-3" /> Editar
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => startEdit(item)}
            className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-text-muted hover:text-accent-neon border border-dashed border-border-subtle rounded-xl transition-colors">
            <Plus className="w-3.5 h-3.5" /> Registrar resultado
          </button>
        )}
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
    <div className="space-y-4 pb-4">
      <div>
        <h1 className="text-2xl font-bold">Resultados</h1>
        <p className="text-sm text-text-muted">Torneios inscritos e resultados</p>
      </div>

      {/* Aviso: resultados são inseridos manualmente */}
      <div className="flex items-start gap-2.5 bg-text-muted/8 border border-border-subtle rounded-xl px-3 py-2.5">
        <PenLine className="w-4 h-4 text-text-muted mt-0.5 shrink-0" />
        <p className="text-xs text-text-muted leading-relaxed">
          <span className="font-semibold text-text-secondary">Inscrições e resultados manuais.</span>{' '}
          Os dados da seção principal foram declarados por você. Os jogos do Tênis Integrado são importados automaticamente pelo seu ID vinculado.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          { label: 'Inscrições',  value: String(items.length),                                                            color: 'text-accent-neon'     },
          { label: 'Vitórias',    value: String(totalWins),                                                               color: 'text-status-open'     },
          { label: 'Derrotas',    value: String(totalLosses),                                                             color: 'text-status-canceled' },
          { label: 'Partidas',    value: String(totalMatches),                                                            color: 'text-accent-blue'     },
        ].map((s) => (
          <div key={s.label} className="card text-center !py-3">
            <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-[10px] text-text-muted mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>
      {bestPosition != null && (
        <div className="card flex items-center gap-3 !py-3">
          <Trophy className="w-6 h-6 text-status-closing shrink-0" />
          <div>
            <div className="text-[10px] text-text-muted">Melhor posição registrada</div>
            <div className="text-xl font-bold text-status-closing">
              {bestPosition === 1 ? '1º lugar' : bestPosition === 2 ? '2º lugar' : bestPosition === 3 ? '3º lugar' : `${bestPosition}º lugar`}
            </div>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card text-center py-12">
          <Award className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="font-semibold mb-2">Nenhuma inscrição ainda</p>
          <p className="text-xs text-text-muted mb-4">
            Na Agenda, marque um torneio como "Inscrito" para acompanhar seus resultados aqui.
          </p>
          <Link to="/watchlist" className="btn-primary inline-flex items-center gap-1 text-sm">
            Ir para Agenda
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {renderGrouped()}
        </div>
      )}

      {/* ── Jogos do Tênis Integrado ─────────────────────────────────────── */}
      {user?.role !== 'parent' && (
        <section className="space-y-2">
          <div className="flex items-center justify-between pt-2">
            <div>
              <h2 className="font-bold">Jogos (Tênis Integrado)</h2>
              <p className="text-xs text-text-muted">Resultados importados automaticamente pelo seu ID</p>
            </div>
            {tiData?.ti_id && (
              <button
                onClick={handleTiSync}
                disabled={tiSyncing}
                className="flex items-center gap-1.5 text-xs text-text-muted hover:text-accent-neon transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${tiSyncing ? 'animate-spin' : ''}`} />
                {tiSyncing ? 'Atualizando...' : 'Atualizar'}
              </button>
            )}
          </div>

          {tiLoading ? (
            <div className="card flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-accent-neon animate-spin" />
            </div>
          ) : !tiData?.has_ti_id ? (
            <div className="card flex items-start gap-3 py-4">
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
            <div className="card text-center py-8">
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
                        {r.round && <span>{r.round}</span>}
                        {r.category && <span>• {r.category}</span>}
                        {r.score && <span>• {r.score}</span>}
                        {r.date && <span>• {r.date}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
              {tiData.is_stale && (
                <p className="text-[10px] text-text-muted text-center">Dados podem estar desatualizados. Clique em Atualizar.</p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
};
