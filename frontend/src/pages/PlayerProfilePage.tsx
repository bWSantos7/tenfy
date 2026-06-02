import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Settings, ExternalLink, Trophy, MapPin, Calendar, User,
  Link as LinkIcon, Loader2, ChevronRight, Ticket, RefreshCw,
  Unlink, X, Search,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { ParentChild, PlayerProfile, TiData, TiRankingEntry, TournamentRegistration, UtrCandidate, WatchlistItem } from '../types';
import { fetchTiData, linkUtr, listChildProfiles, listChildWatchlist, listChildren, listProfiles, searchUtr, syncTiData, syncUtr, unlinkUtr } from '../services/data';
import { myRegistrations } from '../services/registrations';
import { mediaUrl } from '../services/api';
import { resolveAvatar } from '../utils/format';
import { LEVEL_LABELS, GENDER_LABELS, ROLE_LABELS, TENNIS_CLASS_LABELS } from '../utils/format';

const SOURCE_LABELS: Record<string, string> = {
  cbt: 'CBT – Confederação Brasileira de Tênis',
  fpt: 'FPT SP – Federação Paulista',
  fbt: 'FBT – Federação Baiana',
  fct: 'FCT – Federação Cearense',
  cosat: 'COSAT',
  itf: 'ITF',
  utr: 'UTR',
};

const MODALITY_LABELS: Record<string, string> = {
  tennis: 'Tênis',
  beach_tennis: 'Beach Tennis',
  padel: 'Padel',
  wheelchair: 'Tênis em cadeira de rodas',
};

const REG_STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  confirmed: { label: 'Confirmado', cls: 'text-green-400 bg-green-400/10' },
  waiting_list: { label: 'Lista de espera', cls: 'text-yellow-400 bg-yellow-400/10' },
  pending_payment: { label: 'Pag. pendente', cls: 'text-orange-400 bg-orange-400/10' },
  withdrawn: { label: 'Desistiu', cls: 'text-red-400 bg-red-400/10' },
};

function extractTiId(value: unknown): string | null {
  if (!value) return null;
  const s = String(value);
  const m = s.match(/^tenisintegrado:(\d+)$/) || (!s.includes(':') && s.match(/^(\d+)$/));
  return m ? m[1] : null;
}

export const PlayerProfilePage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [children, setChildren] = useState<ParentChild[]>([]);
  const [selectedChildId, setSelectedChildId] = useState<number | null>(null);
  const [childProfiles, setChildProfiles] = useState<PlayerProfile[]>([]);
  const [childActiveRegs, setChildActiveRegs] = useState<WatchlistItem[]>([]);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [loading, setLoading] = useState(true);
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(false);
  const [tiSyncing, setTiSyncing] = useState(false);

  // UTR modal state
  const [utrModalOpen, setUtrModalOpen] = useState(false);
  const [utrQuery, setUtrQuery] = useState('');
  const [utrSearching, setUtrSearching] = useState(false);
  const [utrCandidates, setUtrCandidates] = useState<UtrCandidate[]>([]);
  const [utrError, setUtrError] = useState('');
  const [utrLinking, setUtrLinking] = useState(false);
  const [utrSyncing, setUtrSyncing] = useState(false);

  const isParent = user?.role === 'parent';

  // Initial load: children list (parent) or own profiles (others)
  useEffect(() => {
    if (isParent) {
      Promise.all([
        listChildren().catch(() => [] as ParentChild[]),
        myRegistrations().catch(() => [] as TournamentRegistration[]),
      ]).then(([kids, regs]) => {
        setChildren(kids);
        setRegistrations(regs);
        setSelectedChildId(kids[0]?.child ?? null);
      }).finally(() => setLoading(false));
    } else {
      Promise.all([
        listProfiles().catch(() => [] as PlayerProfile[]),
        myRegistrations().catch(() => [] as TournamentRegistration[]),
      ]).then(([profs, regs]) => {
        setProfiles(profs);
        setRegistrations(regs);
        const primary = profs.find((p) => p.is_primary) ?? profs[0];
        if (primary) {
          setTiLoading(true);
          fetchTiData(primary.id).then((d) => setTiData(d)).catch(() => {}).finally(() => setTiLoading(false));
        }
      }).finally(() => setLoading(false));
    }
  }, [isParent]);

  // When a child is selected, load their profiles, TI data and active registrations
  useEffect(() => {
    if (!isParent || !selectedChildId) return;
    setTiLoading(true);
    setTiData(null);
    setChildProfiles([]);
    setChildActiveRegs([]);
    Promise.all([
      listChildProfiles(selectedChildId),
      listChildWatchlist(selectedChildId).catch(() => [] as WatchlistItem[]),
    ]).then(([profs, wl]) => {
      setChildProfiles(profs);
      setChildActiveRegs(
        wl.filter((i) => i.is_registered || i.user_status === 'registered_declared' || i.user_status === 'completed')
      );
      const primary = profs.find((p) => p.is_primary) ?? profs[0];
      if (primary) return fetchTiData(primary.id);
    })
    .then((d) => { if (d) setTiData(d); })
    .catch(() => {})
    .finally(() => setTiLoading(false));
  }, [isParent, selectedChildId]);

  const activeProfiles = isParent ? childProfiles : profiles;
  const primary = activeProfiles.find((p) => p.is_primary) ?? activeProfiles[0] ?? null;

  async function handleTiSync() {
    if (!primary) return;
    setTiSyncing(true);
    try {
      await syncTiData(primary.id);
      const fresh = await fetchTiData(primary.id);
      setTiData(fresh);
      toast.success('Rankings atualizados com sucesso.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Não foi possível atualizar os dados agora.');
    } finally {
      setTiSyncing(false);
    }
  }
  async function handleUtrSearch() {
    if (!primary || utrQuery.trim().length < 2) return;
    setUtrSearching(true);
    setUtrError('');
    setUtrCandidates([]);
    try {
      const result = await searchUtr(primary.id, utrQuery.trim());
      setUtrCandidates((result.candidates ?? []).slice(0, 3));
      if (!result.candidates?.length) setUtrError('Nenhum perfil encontrado. Tente outro nome.');
    } catch {
      setUtrError('Não foi possível buscar. Verifique sua conexão.');
    } finally {
      setUtrSearching(false);
    }
  }

  async function handleUtrLink(candidate: UtrCandidate) {
    if (!primary || utrLinking) return;
    setUtrLinking(true);
    try {
      await linkUtr(primary.id, candidate);
      const fresh = await listProfiles();
      setProfiles(fresh);
      setUtrModalOpen(false);
      toast.success('Perfil UTR vinculado! Rating sendo extraído em segundo plano.');
    } catch {
      toast.error('Não foi possível vincular o perfil UTR.');
    } finally {
      setUtrLinking(false);
    }
  }

  async function handleUtrUnlink() {
    if (!primary || !window.confirm('Remover vínculo com este perfil UTR?')) return;
    try {
      await unlinkUtr(primary.id);
      const fresh = await listProfiles();
      setProfiles(fresh);
      toast.success('Vínculo UTR removido.');
    } catch {
      toast.error('Não foi possível remover o vínculo UTR.');
    }
  }

  async function handleUtrSync() {
    if (!primary || utrSyncing) return;
    setUtrSyncing(true);
    try {
      await syncUtr(primary.id);
      const fresh = await listProfiles();
      setProfiles(fresh);
      toast.success('Sincronização UTR iniciada.');
    } catch {
      toast.error('Não foi possível sincronizar o UTR agora.');
    } finally {
      setUtrSyncing(false);
    }
  }

  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role ?? ''] ?? user?.role ?? '';

  // Tênis Integrado linked IDs from external_ids
  const tiLinks: { source: string; tiId: string }[] = [];
  if (primary?.external_ids) {
    for (const [src, val] of Object.entries(primary.external_ids)) {
      const tiId = extractTiId(val);
      if (tiId) tiLinks.push({ source: src, tiId });
    }
  }

  const activeRegs = registrations
    .filter((r) => !r.is_withdrawn && ['confirmed', 'waiting_list', 'pending_payment'].includes(r.registration_status))
    .slice(0, 5);

  return (
    <div className="space-y-4 pb-6">

      {/* ── Cabeçalho ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Perfil</h1>
        <Link
          to="/configuracoes"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent-neon/40 transition-colors text-xs font-medium"
          title="Configurações"
        >
          <Settings className="w-4 h-4" />
          <span className="hidden sm:inline">Configurações</span>
        </Link>
      </div>

      {/* ── User card ───────────────────────────────────────────────── */}
      <div className="card flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-accent-neon/20 flex items-center justify-center text-xl font-bold overflow-hidden border-2 border-accent-neon/40 shrink-0">
          {resolveAvatar(user, mediaUrl)
            ? <img src={resolveAvatar(user, mediaUrl)!} alt="avatar" className="w-full h-full object-cover" />
            : <span className="text-accent-neon text-2xl font-bold">{avatarLetter}</span>}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-bold text-lg leading-tight">{user?.full_name || '—'}</h2>
          <p className="text-xs text-text-muted mt-0.5 truncate">{user?.email}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-blue/15 text-accent-blue border border-accent-blue/25">
              {roleLabel}
            </span>
            {primary && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-neon/12 text-accent-neon border border-accent-neon/25">
                {LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level}
              </span>
            )}
          </div>
        </div>
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

      {loading ? (
        <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
      ) : (
        <>
          {/* ── Sem perfil ───────────────────────────────────────────── */}
          {!primary ? (
            <div className="card text-center py-8 space-y-3">
              <User className="w-10 h-10 text-text-muted mx-auto" />
              <p className="font-semibold text-sm">Perfil esportivo não configurado</p>
              <p className="text-xs text-text-muted">Complete seu perfil para ver torneios compatíveis.</p>
              <button className="btn-primary !text-sm" onClick={() => navigate('/onboarding')}>
                Completar perfil
              </button>
            </div>
          ) : (
            <>
              {/* ── Perfil esportivo ─────────────────────────────────── */}
              <section>
                <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Perfil esportivo</h3>
                <div className="card !p-0 overflow-hidden">

                  {/* Name + location header */}
                  <div className="px-5 pt-4 pb-3 border-b border-border-subtle">
                    <h2 className="text-lg font-bold leading-tight">{primary.display_name || '—'}</h2>
                    {(primary.home_city || primary.home_state) && (
                      <div className="flex items-center gap-1.5 mt-1 text-text-muted text-xs">
                        <MapPin className="w-3 h-3 shrink-0" />
                        <span>{[primary.home_city, primary.home_state].filter(Boolean).join(' / ')}</span>
                      </div>
                    )}
                  </div>

                  {/* Key attributes grid */}
                  <div className="grid grid-cols-3 divide-x divide-border-subtle border-b border-border-subtle">
                    {[
                      { label: 'Nível',      value: LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level },
                      { label: 'Modalidade', value: primary.preferred_modality ? (MODALITY_LABELS[primary.preferred_modality] ?? primary.preferred_modality) : '—' },
                      { label: 'Gênero',     value: primary.gender ? (GENDER_LABELS[primary.gender] ?? primary.gender) : '—' },
                    ].map((item) => (
                      <div key={item.label} className="flex flex-col items-center justify-center py-3 gap-0.5 px-2">
                        <span className="text-sm font-bold text-text-primary text-center leading-tight">{item.value}</span>
                        <span className="text-[10px] text-text-muted">{item.label}</span>
                      </div>
                    ))}
                  </div>

                  {/* Secondary info row */}
                  <div className="px-5 py-3 flex items-center gap-4 flex-wrap">
                    {primary.birth_year && (
                      <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                        <Calendar className="w-3.5 h-3.5 text-text-muted shrink-0" />
                        <span>Nasc. {primary.birth_year}</span>
                        {primary.sporting_age != null && (
                          <span className="text-text-muted">({primary.sporting_age} anos)</span>
                        )}
                      </div>
                    )}
                    {primary.tennis_class && (
                      <div className="flex items-center gap-1.5 text-xs">
                        <Trophy className="w-3.5 h-3.5 text-text-muted shrink-0" />
                        <span className="font-semibold px-2 py-0.5 rounded-full bg-accent-neon/12 text-accent-neon border border-accent-neon/25 text-[11px]">
                          {TENNIS_CLASS_LABELS[primary.tennis_class] ?? `Classe ${primary.tennis_class}`}
                        </span>
                      </div>
                    )}
                  </div>

                </div>
              </section>

              {/* ── Categorias ──────────────────────────────────────── */}
              {primary.categories?.length > 0 && (
                <section>
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Categorias compatíveis</h3>
                  <div className="card space-y-2">
                    {primary.categories.slice(0, 8).map((cat) => (
                      <div key={cat.id} className="flex items-center gap-2 text-xs">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cat.is_primary ? 'bg-accent-neon' : 'bg-text-muted'}`} />
                        <span className="flex-1">{cat.category_detail?.label_ptbr ?? cat.category_detail?.code ?? `Cat. ${cat.category}`}</span>
                        {cat.is_primary && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-neon/12 text-accent-neon font-medium">Principal</span>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Rankings (Tênis Integrado) ──────────────────────── */}
              {(tiLoading || tiData?.has_ti_id) && (
                <section>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide">Rankings</h3>
                    {tiData?.ti_id && (
                      <button
                        onClick={handleTiSync}
                        disabled={tiSyncing}
                        className="flex items-center gap-1 text-xs text-text-muted hover:text-accent-neon transition-colors disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${tiSyncing ? 'animate-spin' : ''}`} />
                        {tiSyncing ? 'Atualizando...' : 'Atualizar'}
                      </button>
                    )}
                  </div>

                  {tiLoading ? (
                    <div className="card flex items-center justify-center py-6">
                      <Loader2 className="w-5 h-5 text-accent-neon animate-spin" />
                    </div>
                  ) : tiData?.rankings && tiData.rankings.length > 0 ? (
                    <RankingsDisplay rankings={tiData.rankings} isStale={!!tiData.is_stale} />
                  ) : (
                    <div className="card text-center py-4">
                      <p className="text-xs text-text-muted">Nenhum ranking encontrado no Tênis Integrado.</p>
                    </div>
                  )}
                </section>
              )}

              {/* ── UTR Rating ──────────────────────────────────────── */}
              {!isParent && (
                <section>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide">UTR Rating</h3>
                    {primary?.utr_player_id && (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleUtrSync}
                          disabled={utrSyncing}
                          className="flex items-center gap-1 text-xs text-text-muted hover:text-accent-neon transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${utrSyncing ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={handleUtrUnlink}
                          className="flex items-center gap-1 text-xs text-text-muted hover:text-red-400 transition-colors"
                        >
                          <Unlink className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>

                  {primary?.utr_player_id ? (
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border-subtle">
                        <Trophy className="w-4 h-4 text-accent-neon shrink-0" />
                        <span className="text-xs font-semibold text-accent-neon">UTR — Universal Tennis Rating</span>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mb-3">
                        <div className="text-center">
                          <p className="text-3xl font-black">{primary.utr_singles || '—'}</p>
                          <p className="text-xs text-text-muted mt-1">Simples</p>
                        </div>
                        <div className="text-center">
                          <p className="text-3xl font-black">{primary.utr_doubles || '—'}</p>
                          <p className="text-xs text-text-muted mt-1">Duplas</p>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-text-muted truncate">
                          {primary.utr_display_name || `ID: ${primary.utr_player_id}`}
                        </p>
                        {primary.utr_profile_url && (
                          <a
                            href={primary.utr_profile_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent-blue hover:text-accent-neon transition-colors shrink-0 ml-2"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="card flex items-center gap-3">
                      <Trophy className="w-5 h-5 text-text-muted shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">UTR não vinculado</p>
                        <p className="text-xs text-text-muted">Vincule seu perfil UTR para exibir seu rating.</p>
                      </div>
                      <button
                        onClick={() => { setUtrQuery(primary?.display_name ?? ''); setUtrCandidates([]); setUtrError(''); setUtrModalOpen(true); }}
                        className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded-lg bg-accent-neon/15 text-accent-neon border border-accent-neon/30 hover:bg-accent-neon/25 transition-colors"
                      >
                        Vincular
                      </button>
                    </div>
                  )}
                </section>
              )}

              {/* ── Modal busca UTR ──────────────────────────────────── */}
              {utrModalOpen && primary && (
                <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                  <div className="bg-bg-card border border-border-subtle rounded-2xl w-full max-w-md max-h-[85vh] overflow-y-auto shadow-2xl">
                    <div className="flex items-center justify-between p-5 border-b border-border-subtle sticky top-0 bg-bg-card rounded-t-2xl">
                      <div>
                        <h2 className="text-base font-bold">Vincular perfil UTR</h2>
                        <p className="text-xs text-text-muted mt-0.5">Busque seu nome e confirme qual perfil é o seu.</p>
                      </div>
                      <button onClick={() => setUtrModalOpen(false)} className="text-text-muted hover:text-text-primary transition-colors">
                        <X className="w-5 h-5" />
                      </button>
                    </div>

                    <div className="p-5 space-y-4">
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={utrQuery}
                          onChange={(e) => setUtrQuery(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleUtrSearch()}
                          placeholder="Nome do atleta..."
                          className="flex-1 bg-bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-neon transition-colors"
                        />
                        <button
                          onClick={handleUtrSearch}
                          disabled={utrSearching || utrQuery.trim().length < 2}
                          className="px-4 py-2 rounded-lg bg-accent-neon text-bg-base font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
                        >
                          {utrSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                        </button>
                      </div>

                      {utrError && <p className="text-xs text-red-400">{utrError}</p>}

                      {utrCandidates.map((c) => (
                        <div key={c.utr_player_id} className="border border-border-subtle rounded-xl p-4 space-y-3">
                          <div>
                            <p className="font-semibold text-sm">{c.display_name}</p>
                            <p className="text-xs text-text-muted mt-0.5">
                              {[c.country, c.location].filter(Boolean).join(' · ')}
                            </p>
                          </div>
                          {(c.singles_utr || c.doubles_utr) ? (
                            <div className="flex gap-6">
                              <div className="text-center">
                                <p className="text-2xl font-black">{c.singles_utr || '—'}</p>
                                <p className="text-[10px] text-text-muted">UTR Simples</p>
                              </div>
                              <div className="text-center">
                                <p className="text-2xl font-black">{c.doubles_utr || '—'}</p>
                                <p className="text-[10px] text-text-muted">UTR Duplas</p>
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-text-muted italic">
                              Rating será extraído automaticamente após confirmar o perfil.
                            </p>
                          )}
                          <p className="text-[10px] text-text-muted">ID: {c.utr_player_id}</p>
                          <button
                            onClick={() => handleUtrLink(c)}
                            disabled={utrLinking}
                            className="w-full py-2 rounded-lg bg-accent-neon/15 border border-accent-neon/30 text-accent-neon text-sm font-semibold hover:bg-accent-neon/25 transition-colors disabled:opacity-50"
                          >
                            {utrLinking ? 'Salvando...' : 'Este sou eu'}
                          </button>
                        </div>
                      ))}

                      <button
                        onClick={() => setUtrModalOpen(false)}
                        className="w-full py-2 text-sm text-text-muted hover:text-text-primary transition-colors"
                      >
                        Não sou nenhum desses
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Vínculos Tênis Integrado ─────────────────────────── */}
              {tiLinks.length > 0 && (
                <section>
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Vínculos externos</h3>
                  <div className="card divide-y divide-border-subtle">
                    {tiLinks.map(({ source, tiId }) => (
                      <a
                        key={source}
                        href={`https://www.tenisintegrado.com.br/perfil2/index/${tiId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-3 py-3 first:pt-0 last:pb-0 group"
                      >
                        <div className="w-8 h-8 rounded-lg bg-accent-blue/15 flex items-center justify-center shrink-0">
                          <LinkIcon className="w-4 h-4 text-accent-blue" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium leading-tight">{SOURCE_LABELS[source] ?? source.toUpperCase()}</p>
                          <p className="text-xs text-text-muted mt-0.5">ID: {tiId} · Tênis Integrado</p>
                        </div>
                        <ExternalLink className="w-4 h-4 text-text-muted group-hover:text-accent-blue transition-colors shrink-0" />
                      </a>
                    ))}
                    <p className="text-[10px] text-text-muted pt-3">
                      Clique para visualizar seu perfil na plataforma de origem.
                    </p>
                  </div>
                </section>
              )}
            </>
          )}

          {/* ── Inscrições ativas ───────────────────────────────────── */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide">Inscrições ativas</h3>
              <Link to="/inscricoes" className="text-xs text-accent-blue hover:underline flex items-center gap-0.5">
                Ver todas <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            {isParent ? (
              childActiveRegs.length === 0 ? (
                <div className="card text-center py-6 space-y-2">
                  <Ticket className="w-8 h-8 text-text-muted mx-auto" />
                  <p className="text-xs text-text-muted">Nenhuma inscrição ativa encontrada.</p>
                </div>
              ) : (
                <div className="card divide-y divide-border-subtle">
                  {childActiveRegs.slice(0, 5).map((item) => (
                    <div key={item.id} className="py-3 first:pt-0 last:pb-0 space-y-1">
                      <p className="text-sm font-semibold leading-tight line-clamp-2">{item.edition_detail.tournament_name}</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${item.is_registered ? 'text-green-400 bg-green-400/10' : 'text-yellow-400 bg-yellow-400/10'}`}>
                          {item.is_registered ? 'Inscrição Confirmada' : 'Declarado manualmente'}
                        </span>
                      </div>
                      {item.edition_detail.start_date && (
                        <p className="text-xs text-text-muted">
                          {new Date(item.edition_detail.start_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )
            ) : activeRegs.length === 0 ? (
              <div className="card text-center py-6 space-y-2">
                <Ticket className="w-8 h-8 text-text-muted mx-auto" />
                <p className="text-xs text-text-muted">Nenhuma inscrição ativa encontrada.</p>
                <Link to="/torneios" className="text-xs text-accent-neon hover:underline">Ver torneios disponíveis</Link>
              </div>
            ) : (
              <div className="card divide-y divide-border-subtle">
                {activeRegs.map((reg) => {
                  const st = REG_STATUS_LABELS[reg.registration_status] ?? { label: reg.registration_status, cls: 'text-text-muted bg-text-muted/10' };
                  return (
                    <div key={reg.id} className="py-3 first:pt-0 last:pb-0 space-y-1">
                      <p className="text-sm font-semibold leading-tight line-clamp-2">{reg.edition_title}</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        {reg.category_text && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-neon/10 text-accent-neon">{reg.category_text}</span>
                        )}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${st.cls}`}>{st.label}</span>
                      </div>
                      {reg.edition_start_date && (
                        <p className="text-xs text-text-muted">
                          {new Date(reg.edition_start_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};

// ── RankingsDisplay ───────────────────────────────────────────────────────────

function RankingsDisplay({ rankings, isStale }: { rankings: TiRankingEntry[]; isStale: boolean }) {
  const wtn = rankings.filter((r) => r.federation === 'World Tennis Number');
  const fed = rankings.filter((r) => r.federation !== 'World Tennis Number');

  return (
    <div className="space-y-3">
      {/* WTN block */}
      {wtn.length > 0 && (
        <div className="card !p-0 overflow-hidden">
          <div className="px-4 py-2.5 bg-bg-elevated/60 border-b border-border-subtle flex items-center gap-2">
            <Trophy className="w-3.5 h-3.5 text-accent-blue shrink-0" />
            <span className="text-xs font-bold text-accent-blue">WTN — World Tennis Number</span>
          </div>
          <div className="grid grid-cols-2 divide-x divide-border-subtle">
            {wtn.map((r, i) => (
              <div key={i} className="flex flex-col items-center justify-center py-4 gap-1">
                <span className="text-2xl font-black text-text-primary tabular-nums">{r.points ?? '—'}</span>
                <span className="text-[11px] text-text-muted font-medium">{r.modality || r.category}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Federation rankings */}
      {fed.length > 0 && (
        <div className="card !p-0 overflow-hidden">
          <div className="px-4 py-2.5 bg-bg-elevated/60 border-b border-border-subtle">
            <span className="text-xs font-bold text-text-muted">Rankings federativos</span>
          </div>
          <div className="divide-y divide-border-subtle">
            {fed.map((r, i) => {
              const pos = r.position ? Number(r.position) : null;
              const medalColor =
                pos === 1 ? 'text-yellow-400 bg-yellow-400/15 border-yellow-400/30' :
                pos === 2 ? 'text-slate-300 bg-slate-300/15 border-slate-300/30' :
                pos === 3 ? 'text-amber-600 bg-amber-600/15 border-amber-600/30' :
                'text-accent-neon bg-accent-neon/12 border-accent-neon/25';

              return (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  {/* Position */}
                  <div className={`w-11 h-11 rounded-xl flex flex-col items-center justify-center border shrink-0 ${pos ? medalColor : 'text-text-muted bg-bg-elevated border-border-subtle'}`}>
                    {pos ? (
                      <span className="text-sm font-black leading-none">{pos}º</span>
                    ) : (
                      <span className="text-xs text-text-muted">—</span>
                    )}
                  </div>

                  {/* Name + federation + date */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold leading-snug line-clamp-2">{r.ranking_name || r.category || '—'}</p>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      {r.federation && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent-blue/12 text-accent-blue font-medium border border-accent-blue/20">
                          {r.federation}
                        </span>
                      )}
                      {r.date && (
                        <span className="text-[10px] text-text-muted">{r.date}</span>
                      )}
                    </div>
                  </div>

                  {/* Points */}
                  {r.points && (
                    <div className="text-right shrink-0">
                      <span className="text-base font-black text-text-primary tabular-nums">{r.points}</span>
                      <p className="text-[10px] text-text-muted">pontos</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {isStale && (
        <p className="text-[10px] text-text-muted text-center">Dados podem estar desatualizados. Clique em Atualizar.</p>
      )}
    </div>
  );
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-text-muted shrink-0 w-4 flex justify-center">{icon}</span>
      <span className="text-text-muted w-28 shrink-0 text-xs">{label}</span>
      <span className="font-medium truncate">{value}</span>
    </div>
  );
}
