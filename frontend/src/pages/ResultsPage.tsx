import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Award, Trophy, Loader2, Plus, Check, X, Edit2, User } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem, PlayerProfile } from '../types';
import { listWatchlist, saveResult, listProfiles } from '../services/data';
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

  async function load() {
    setLoading(true);
    try {
      const [data, profs] = await Promise.all([
        listWatchlist(),
        listProfiles().catch(() => [] as PlayerProfile[]),
      ]);
      // Show inscribed (declared) OR tournaments with existing results
      setItems(data.filter((i) => i.user_status === 'registered_declared' || !!i.result));
      setProfileNames(Object.fromEntries(profs.map((p) => [p.id, p.display_name])));
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

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
            <button onClick={() => startEdit(item)}
              className="w-full flex items-center justify-center gap-1.5 py-1.5 text-xs text-text-muted hover:text-accent-neon border border-dashed border-border-subtle rounded-xl transition-colors">
              <Edit2 className="w-3 h-3" /> Editar resultado
            </button>
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

      {items.length > 0 && (
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Inscritos', value: items.length,   color: 'text-accent-neon'      },
            { label: 'Vitórias',  value: totalWins,      color: 'text-status-open'      },
            { label: 'Derrotas',  value: totalLosses,    color: 'text-status-canceled'  },
            { label: 'Partidas',  value: totalMatches,   color: 'text-accent-blue'      },
          ].map((s) => (
            <div key={s.label} className="card text-center !py-3">
              <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-[10px] text-text-muted mt-0.5">{s.label}</div>
            </div>
          ))}
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
    </div>
  );
};
