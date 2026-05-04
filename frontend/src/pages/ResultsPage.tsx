import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Award, Trophy, Loader2, Plus, Check, X, Edit2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { WatchlistItem } from '../types';
import { listWatchlist, saveResult } from '../services/data';
import { extractApiError } from '../services/api';
import { fmtDateRange } from '../utils/format';

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
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState<ResultForm>(emptyForm());
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await listWatchlist();
      // Only completed or items with existing results
      const finished = data.filter(
        (i) => i.user_status === 'completed' || i.result,
      );
      setItems(finished);
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
        category_played: form.category_played,
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

  const totalWins = items.reduce((s, i) => s + (i.result?.wins ?? 0), 0);
  const totalLosses = items.reduce((s, i) => s + (i.result?.losses ?? 0), 0);
  const withPosition = items.filter((i) => i.result?.position === 1).length;

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
        <h1 className="text-2xl font-bold">Meus Resultados</h1>
        <p className="text-sm text-text-muted">Histórico de participações e desempenho em torneios</p>
      </div>

      {items.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="card text-center !py-3">
            <div className="text-2xl font-bold text-accent-neon">{items.length}</div>
            <div className="text-xs text-text-muted mt-1">Torneios</div>
          </div>
          <div className="card text-center !py-3">
            <div className="text-2xl font-bold text-accent-blue">{totalWins}V / {totalLosses}D</div>
            <div className="text-xs text-text-muted mt-1">Vitórias / Derrotas</div>
          </div>
          <div className="card text-center !py-3">
            <div className="text-2xl font-bold text-status-closing">{withPosition}</div>
            <div className="text-xs text-text-muted mt-1">Títulos (1º lugar)</div>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card text-center py-12">
          <Award className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="text-sm text-text-secondary mb-2">Nenhum resultado registrado ainda.</p>
          <p className="text-xs text-text-muted mb-4">
            Marque torneios como "Concluído" na sua agenda e registre seus resultados aqui.
          </p>
          <Link to="/watchlist" className="btn-primary inline-flex items-center gap-1 text-sm">
            Ver minha agenda
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
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
                {item.result?.position === 1 && (
                  <Trophy className="w-5 h-5 text-status-closing shrink-0" />
                )}
              </div>

              {editing === item.id ? (
                <div className="space-y-3 border-t border-border-subtle pt-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-text-muted mb-1 block">Categoria jogada</label>
                      <input
                        className="input-base !py-2 text-sm"
                        placeholder="Ex: 4M3 Masculino"
                        value={form.category_played}
                        onChange={(e) => setForm((f) => ({ ...f, category_played: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-text-muted mb-1 block">Colocação final</label>
                      <input
                        type="number"
                        min={1}
                        className="input-base !py-2 text-sm"
                        placeholder="1 = Campeão"
                        value={form.position}
                        onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-text-muted mb-1 block">Vitórias</label>
                      <input
                        type="number"
                        min={0}
                        className="input-base !py-2 text-sm"
                        value={form.wins}
                        onChange={(e) => setForm((f) => ({ ...f, wins: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-text-muted mb-1 block">Derrotas</label>
                      <input
                        type="number"
                        min={0}
                        className="input-base !py-2 text-sm"
                        value={form.losses}
                        onChange={(e) => setForm((f) => ({ ...f, losses: e.target.value }))}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted mb-1 block">Observações</label>
                    <textarea
                      rows={2}
                      className="input-base text-sm resize-none"
                      placeholder="Notas pessoais sobre o torneio..."
                      value={form.notes}
                      onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn-secondary !py-2 flex-1 flex items-center justify-center gap-1 text-sm"
                      onClick={() => setEditing(null)}
                    >
                      <X className="w-3.5 h-3.5" /> Cancelar
                    </button>
                    <button
                      className="btn-primary !py-2 flex-1 flex items-center justify-center gap-1 text-sm"
                      onClick={() => handleSave(item.id)}
                      disabled={saving}
                    >
                      {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                      Salvar
                    </button>
                  </div>
                </div>
              ) : item.result ? (
                <div className="border-t border-border-subtle pt-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex gap-4 text-sm">
                      {item.result.category_played && (
                        <span className="text-text-secondary">{item.result.category_played}</span>
                      )}
                      {item.result.position && (
                        <span className="font-semibold text-accent-neon">{item.result.position}º lugar</span>
                      )}
                      <span className="text-text-muted">
                        {item.result.wins}V / {item.result.losses}D
                      </span>
                    </div>
                    <button
                      onClick={() => startEdit(item)}
                      className="p-1 rounded hover:bg-bg-elevated text-text-muted hover:text-text-primary"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {item.result.notes && (
                    <p className="text-xs text-text-muted">{item.result.notes}</p>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => startEdit(item)}
                  className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-text-muted hover:text-accent-neon border border-dashed border-border-subtle rounded-xl transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" /> Registrar resultado
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
