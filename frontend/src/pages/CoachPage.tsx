import React, { useEffect, useState } from 'react';
import { Users, Plus, Trash2, ChevronRight, ChevronLeft, Star, Trophy, Calendar, X } from 'lucide-react';
import { CoachAthlete, WatchlistItem } from '../types';
import { addAthlete, getAthleteWatchlist, listAthletes, removeAthlete } from '../services/data';
import { extractApiError } from '../services/api';

type View = 'roster' | 'watchlist';

const STATUS_LABEL: Record<string, string> = {
  none: 'Sem status',
  intended: 'Pretende inscrever',
  registered_declared: 'Inscrito',
  withdrawn: 'Desistiu',
  completed: 'Concluído',
};

const STATUS_COLOR: Record<string, string> = {
  none: 'text-text-secondary',
  intended: 'text-accent-blue',
  registered_declared: 'text-accent-neon',
  withdrawn: 'text-red-400',
  completed: 'text-yellow-400',
};

export const CoachPage: React.FC = () => {
  const [athletes, setAthletes] = useState<CoachAthlete[]>([]);
  const [loading, setLoading] = useState(true);
  const [emailInput, setEmailInput] = useState('');
  const [notesInput, setNotesInput] = useState('');
  const [addError, setAddError] = useState('');
  const [addLoading, setAddLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const [view, setView] = useState<View>('roster');
  const [selectedAthlete, setSelectedAthlete] = useState<CoachAthlete | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);

  useEffect(() => {
    fetchAthletes();
  }, []);

  async function fetchAthletes() {
    setLoading(true);
    try {
      const data = await listAthletes();
      setAthletes(data);
    } catch {
      // silence
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!emailInput.trim()) return;
    setAddLoading(true);
    setAddError('');
    try {
      const newLink = await addAthlete(emailInput.trim(), notesInput.trim());
      setAthletes(prev => [newLink, ...prev]);
      setEmailInput('');
      setNotesInput('');
      setShowAddForm(false);
    } catch (err: unknown) {
      setAddError(extractApiError(err));
    } finally {
      setAddLoading(false);
    }
  }

  async function handleRemove(id: number) {
    if (!confirm('Remover esse aluno da sua lista?')) return;
    await removeAthlete(id);
    setAthletes(prev => prev.filter(a => a.id !== id));
    if (selectedAthlete?.id === id) {
      setView('roster');
      setSelectedAthlete(null);
    }
  }

  async function openWatchlist(athlete: CoachAthlete) {
    setSelectedAthlete(athlete);
    setView('watchlist');
    setWatchlistLoading(true);
    try {
      const data = await getAthleteWatchlist(athlete.id);
      setWatchlist(data.watchlist);
    } catch {
      setWatchlist([]);
    } finally {
      setWatchlistLoading(false);
    }
  }

  function backToRoster() {
    setView('roster');
    setSelectedAthlete(null);
    setWatchlist([]);
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        {view === 'watchlist' && selectedAthlete ? (
          <button onClick={backToRoster} className="flex items-center gap-1 text-accent-blue hover:underline text-sm">
            <ChevronLeft size={16} />
            Meus alunos
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <Users size={22} className="text-accent-neon" />
            <h1 className="text-xl font-bold text-text-primary">Modo Treinador</h1>
          </div>
        )}
        {view === 'roster' && (
          <button
            onClick={() => { setShowAddForm(v => !v); setAddError(''); }}
            className="flex items-center gap-1 text-sm bg-accent-neon/10 text-accent-neon border border-accent-neon/30 rounded-lg px-3 py-1.5 hover:bg-accent-neon/20 transition-colors"
          >
            <Plus size={15} />
            Adicionar aluno
          </button>
        )}
      </div>

      {/* Add-athlete form */}
      {view === 'roster' && showAddForm && (
        <form onSubmit={handleAdd} className="bg-bg-card border border-border-subtle rounded-xl p-4 space-y-3">
          <p className="text-sm font-medium text-text-primary">Adicionar aluno por email</p>
          <input
            type="email"
            placeholder="email@exemplo.com"
            value={emailInput}
            onChange={e => setEmailInput(e.target.value)}
            required
            className="w-full rounded-lg bg-bg-base border border-border-subtle px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-neon"
          />
          <input
            type="text"
            placeholder="Observações (opcional)"
            value={notesInput}
            onChange={e => setNotesInput(e.target.value)}
            maxLength={300}
            className="w-full rounded-lg bg-bg-base border border-border-subtle px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-neon"
          />
          {addError && <p className="text-red-400 text-xs">{addError}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={addLoading}
              className="flex-1 bg-accent-neon text-bg-base font-semibold rounded-lg py-2 text-sm hover:bg-accent-neon/90 disabled:opacity-50 transition-colors"
            >
              {addLoading ? 'Adicionando…' : 'Adicionar'}
            </button>
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="px-4 rounded-lg border border-border-subtle text-text-secondary text-sm hover:bg-bg-card transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        </form>
      )}

      {/* Roster list */}
      {view === 'roster' && (
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-12 text-text-muted text-sm">Carregando…</div>
          ) : athletes.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <Users size={40} className="mx-auto text-text-muted/40" />
              <p className="text-text-secondary text-sm">Nenhum aluno adicionado ainda.</p>
              <p className="text-text-muted text-xs">Use o botão acima para adicionar alunos pelo email deles.</p>
            </div>
          ) : (
            athletes.map(link => (
              <div key={link.id} className="bg-bg-card border border-border-subtle rounded-xl p-4 flex items-center gap-3">
                {link.athlete_detail.avatar ? (
                  <img
                    src={link.athlete_detail.avatar}
                    alt=""
                    className="w-10 h-10 rounded-full object-cover shrink-0"
                  />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-accent-neon/20 flex items-center justify-center shrink-0">
                    <span className="text-accent-neon font-bold text-sm">
                      {(link.athlete_detail.full_name || link.athlete_detail.email)[0].toUpperCase()}
                    </span>
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-text-primary text-sm truncate">
                    {link.athlete_detail.full_name || link.athlete_detail.email}
                  </p>
                  {link.athlete_detail.full_name && (
                    <p className="text-text-muted text-xs truncate">{link.athlete_detail.email}</p>
                  )}
                  {link.notes && (
                    <p className="text-text-secondary text-xs truncate mt-0.5">{link.notes}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => openWatchlist(link)}
                    className="flex items-center gap-1 text-xs text-accent-blue hover:underline px-2 py-1"
                  >
                    Ver watchlist
                    <ChevronRight size={13} />
                  </button>
                  <button
                    onClick={() => handleRemove(link.id)}
                    className="text-text-muted hover:text-red-400 p-1.5 rounded transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Athlete watchlist view */}
      {view === 'watchlist' && selectedAthlete && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-accent-neon/20 flex items-center justify-center">
              <span className="text-accent-neon font-bold text-xs">
                {(selectedAthlete.athlete_detail.full_name || selectedAthlete.athlete_detail.email)[0].toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-semibold text-text-primary text-sm">
                {selectedAthlete.athlete_detail.full_name || selectedAthlete.athlete_detail.email}
              </p>
              <p className="text-text-muted text-xs">Watchlist do aluno</p>
            </div>
          </div>

          {watchlistLoading ? (
            <div className="text-center py-12 text-text-muted text-sm">Carregando…</div>
          ) : watchlist.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <Calendar size={40} className="mx-auto text-text-muted/40" />
              <p className="text-text-secondary text-sm">Esse aluno não tem torneios na watchlist.</p>
            </div>
          ) : (
            watchlist.map(item => (
              <div key={item.id} className="bg-bg-card border border-border-subtle rounded-xl p-4 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-text-primary text-sm leading-snug">
                    {item.edition_detail.title}
                  </p>
                  <span className={`text-xs shrink-0 ${STATUS_COLOR[item.user_status]}`}>
                    {STATUS_LABEL[item.user_status]}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-text-muted">
                  <span>{item.edition_detail.organization_short}</span>
                  {item.edition_detail.start_date && (
                    <span>
                      {new Date(item.edition_detail.start_date).toLocaleDateString('pt-BR', {
                        day: '2-digit', month: 'short', year: 'numeric',
                      })}
                    </span>
                  )}
                  {item.edition_detail.venue_city && (
                    <span>{item.edition_detail.venue_city} – {item.edition_detail.venue_state}</span>
                  )}
                </div>
                {item.result && (
                  <div className="mt-2 flex items-center gap-2 text-xs text-yellow-400">
                    <Trophy size={12} />
                    <span>
                      {item.result.category_played && `${item.result.category_played} · `}
                      {item.result.position ? `${item.result.position}º lugar · ` : ''}
                      {item.result.wins}V / {item.result.losses}D
                    </span>
                    {item.result.position === 1 && <Star size={12} className="fill-yellow-400" />}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
