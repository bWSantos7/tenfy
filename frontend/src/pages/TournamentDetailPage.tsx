import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft, Calendar, MapPin, Clock, ExternalLink, Star, CheckCircle2,
  XCircle, HelpCircle, Loader2, AlertTriangle, FileText, History, Share2,
  Users, ChevronDown, ChevronUp, RefreshCw, ShieldCheck, Info, AlertCircle,
  CheckCircle, CreditCard, UserX, UserPlus, Trophy, LogIn, Lock, DoorOpen,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  TournamentEditionDetail, EditionEligibility, PlayerProfile,
  EditionRegistrants, RegistrantCategory, FederationEntryItem, TournamentRegistration,
} from '../types';
import { getEdition, evaluateEdition } from '../services/tournaments';
import { listProfiles, toggleWatchlist, listWatchlist, updateWatch } from '../services/data';
import { getEditionRegistrants, myRegistrations, withdrawRegistration } from '../services/registrations';
import { fmtDate } from '../utils/format';
import {
  STATUS_LABELS, fmtDateRange, fmtDateTime, fmtBRL, fmtRelative,
  statusBgClass, translateReason, formatChangeEventTitle, formatChangeEventDetails,
} from '../utils/format';
import { extractApiError } from '../services/api';
import { pickBestProfile } from '../utils/profile';
import { useAuth } from '../contexts/AuthContext';
import { getActiveProfileId } from '../utils/activeProfile';

const STALE_HOURS = 24;
function isStale(syncedAt: string | null): boolean {
  if (!syncedAt) return false;
  return Date.now() - new Date(syncedAt).getTime() > STALE_HOURS * 3600 * 1000;
}

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  confirmed:       { icon: <CheckCircle  className="w-3.5 h-3.5" />, color: 'text-accent-neon',    label: 'Confirmado na chave' },
  waiting_list:    { icon: <Clock        className="w-3.5 h-3.5" />, color: 'text-status-closing', label: 'Lista de espera' },
  pending_payment: { icon: <CreditCard   className="w-3.5 h-3.5" />, color: 'text-accent-blue',    label: 'Aguardando pagamento' },
  registered:      { icon: <UserPlus     className="w-3.5 h-3.5" />, color: 'text-text-secondary', label: 'Inscrito' },
  removed:         { icon: <UserX        className="w-3.5 h-3.5" />, color: 'text-status-canceled',label: 'Removido' },
};

const PAYMENT_COLOR: Record<string, string> = {
  paid:    'text-accent-neon',
  pending: 'text-status-closing',
  unknown: 'text-text-muted',
};

const CONFIDENCE_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  high:   { icon: <ShieldCheck className="w-2.5 h-2.5" />, color: 'text-accent-neon',    label: 'Fonte oficial' },
  medium: { icon: <Info        className="w-2.5 h-2.5" />, color: 'text-status-closing', label: 'Fonte pública' },
  med:    { icon: <Info        className="w-2.5 h-2.5" />, color: 'text-status-closing', label: 'Fonte pública' },
  low:    { icon: <AlertCircle className="w-2.5 h-2.5" />, color: 'text-status-canceled',label: 'Dado inferido' },
};

export const TournamentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { user } = useAuth();
  const [ed, setEd] = useState<TournamentEditionDetail | null>(null);
  const [elig, setElig] = useState<EditionEligibility | null>(null);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [watching, setWatching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [togglingWatch, setTogglingWatch] = useState(false);
  const [registrants, setRegistrants] = useState<EditionRegistrants | null>(null);
  const [registrantsLoading, setRegistrantsLoading] = useState(false);
  const [registrantsOpen, setRegistrantsOpen] = useState(false);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [myReg, setMyReg] = useState<TournamentRegistration | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);

  async function handleShare() {
    const url = window.location.href;
    const title = ed?.title ?? 'Torneio';
    if (navigator.share) {
      try { await navigator.share({ title, url }); } catch { /* cancelled */ }
    } else {
      await navigator.clipboard.writeText(url);
      toast.success('Link copiado!');
    }
  }

  useEffect(() => {
    if (!id) return;
    const edId = Number(id);
    (async () => {
      setLoading(true);
      try {
        const [edition, profiles, watchlist, regs] = await Promise.all([
          getEdition(edId),
          listProfiles().catch(() => []),
          listWatchlist().catch(() => []),
          myRegistrations().catch(() => [] as TournamentRegistration[]),
        ]);
        setEd(edition);
        // Respect active profile: parent viewing as dependent should use the
        // dependent's profile so watchlist and eligibility target the right player.
        const profileList = Array.isArray(profiles) ? profiles : (profiles as any).results ?? [];
        let primary: PlayerProfile | null = null;
        if (user?.role === 'parent' && user.id) {
          const activeId = getActiveProfileId(user.id);
          if (activeId) primary = profileList.find((p: any) => p.id === activeId) ?? null;
        }
        if (!primary) primary = pickBestProfile(profileList);
        setProfile(primary);
        const watchItem = watchlist.find((w) => w.edition === edId);
        setWatching(!!watchItem);
        const existing = regs.find((r) => r.edition_id === edId && !r.is_withdrawn);
        setMyReg(existing ?? null);
        if (primary) {
          try {
            const e = await evaluateEdition(edId, primary.id);
            setElig(e);
          } catch { /* ignore */ }
        }
      } catch (err) {
        toast.error(extractApiError(err));
        nav('/torneios');
      } finally {
        setLoading(false);
      }
    })();
  }, [id, nav]);

  async function loadRegistrants(edId: number) {
    setRegistrantsLoading(true);
    try {
      const data = await getEditionRegistrants(edId);
      setRegistrants(data);
      if (data.categories.length > 0) {
        setExpandedCats(new Set([data.categories[0].category_text]));
      }
    } catch {
      toast.error('Não foi possível carregar os inscritos.');
    } finally {
      setRegistrantsLoading(false);
    }
  }

  async function handleToggleRegistrants() {
    if (!ed) return;
    if (registrantsOpen) {
      setRegistrantsOpen(false);
      return;
    }
    setRegistrantsOpen(true);
    if (!registrants) await loadRegistrants(ed.id);
  }

  async function handleRefreshRegistrants() {
    if (!ed) return;
    setRegistrants(null);
    setExpandedCats(new Set());
    await loadRegistrants(ed.id);
  }

  function toggleCat(text: string) {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(text)) next.delete(text); else next.add(text);
      return next;
    });
  }

  async function handleWithdraw() {
    if (!myReg) return;
    const ok = window.confirm('Tem certeza que deseja cancelar sua inscrição neste torneio?');
    if (!ok) return;
    setWithdrawing(true);
    try {
      await withdrawRegistration(myReg.id);
      setMyReg(null);
      toast.success('Inscrição cancelada.');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setWithdrawing(false);
    }
  }

  async function handleWatch() {
    if (!ed) return;
    setTogglingWatch(true);
    try {
      const r = await toggleWatchlist(ed.id, profile?.id);
      setWatching(r.watching);
      toast.success(r.watching ? 'Adicionado à sua agenda' : 'Removido da agenda');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setTogglingWatch(false);
    }
  }

  if (loading || !ed) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  const status = ed.dynamic_status || ed.status;
  const statusLabel = STATUS_LABELS[status];
  const location = [
    ed.venue_detail?.name && ed.venue_detail.name !== 'CBT' ? ed.venue_detail.name : null,
    [ed.venue_city, ed.venue_state].filter(Boolean).join('/'),
  ].filter(Boolean).join(' • ');
  const regLink = ed.links.find((l) => l.link_type === 'registration') || null;
  const regURL = regLink?.url || ed.official_source_url;
  const regulation = ed.links.find((l) => l.link_type === 'regulation') || null;

  const compatCats = (elig?.categories || []).filter((c) => c.result.status === 'compatible');
  const unknownCats = (elig?.categories || []).filter((c) => c.result.status === 'unknown');
  const incompatCats = (elig?.categories || []).filter((c) => c.result.status === 'incompatible');

  // Staleness / sync info from registrants
  const firstEntry = registrants?.categories[0]?.entries[0];
  const syncedAt = firstEntry?.synced_at ?? null;
  const sourceLabel = firstEntry?.source_label || firstEntry?.source || null;

  return (
    <div className="space-y-4 pb-4">
      <button onClick={() => nav(-1)} className="btn-ghost flex items-center gap-1 -ml-2">
        <ArrowLeft className="w-4 h-4" /> Voltar
      </button>

      {/* ── Main info card ── */}
      <div className="card space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold text-accent-blue uppercase tracking-wider">
              {ed.tournament_detail.organization_detail.short_name ||
                ed.tournament_detail.organization_detail.name}
              {ed.tournament_detail.circuit && ` • ${ed.tournament_detail.circuit}`}
            </div>
            <h1 className="text-xl font-bold leading-tight mt-1">{ed.title}</h1>
          </div>
          <div className={`badge border ${statusBgClass(status)} shrink-0`}>
            {statusLabel}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm pt-2">
          <Stat icon={<Calendar className="w-4 h-4" />} label="Período"
            value={fmtDateRange(ed.start_date, ed.end_date)} />
          <Stat icon={<MapPin className="w-4 h-4" />} label="Local"
            value={location || '—'} />
          <Stat icon={<Clock className="w-4 h-4" />} label="Prazo de inscrição"
            value={ed.entry_close_at ? fmtDateTime(ed.entry_close_at) : '—'}
            accent={!!ed.entry_close_at} />
          <Stat icon={<FileText className="w-4 h-4" />} label="Valor base"
            value={fmtBRL(ed.base_price_brl)} />
        </div>

        {ed.venue_detail?.address && (
          <div className="text-xs text-text-secondary pt-1">
            Endereço: {ed.venue_detail.address}
          </div>
        )}

        {ed.is_manual_override && (
          <div className="flex items-start gap-2 text-xs bg-accent-blue/10 border border-accent-blue/30 rounded-lg p-2">
            <AlertTriangle className="w-4 h-4 text-accent-blue shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-accent-blue">Dados validados manualmente</div>
              <div className="text-text-secondary">
                {ed.reviewed_by_email && `Revisado por ${ed.reviewed_by_email}. `}
                Alterações automáticas suspensas para este torneio.
              </div>
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            className={`flex items-center justify-center gap-2 ${watching ? 'btn-secondary !border-accent-neon !text-accent-neon' : 'btn-primary'}`}
            onClick={handleWatch} disabled={togglingWatch}
          >
            {togglingWatch
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Star className={`w-4 h-4 ${watching ? 'fill-accent-neon' : ''}`} />}
            {watching ? 'Na sua agenda' : 'Acompanhar'}
          </button>
          {regURL && (
            <a href={regURL} target="_blank" rel="noopener noreferrer"
              className="btn-secondary flex items-center justify-center gap-2">
              <ExternalLink className="w-4 h-4" /> Site oficial
            </a>
          )}
        </div>

        {/* Ver lista de inscritos — mesma posição do mobile */}
        <button
          onClick={handleToggleRegistrants}
          disabled={registrantsLoading}
          className="w-full btn-secondary flex items-center justify-center gap-2"
        >
          {registrantsLoading
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <Users className="w-4 h-4" />}
          {registrantsOpen ? 'Ocultar lista de inscritos' : 'Ver lista de inscritos'}
        </button>

        <button
          onClick={handleShare}
          className="w-full btn-ghost flex items-center justify-center gap-2 text-sm border border-border-subtle rounded-xl py-2"
        >
          <Share2 className="w-4 h-4" /> Compartilhar torneio
        </button>

        {regulation && (
          <a href={regulation.url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-accent-blue hover:underline inline-flex items-center gap-1">
            <FileText className="w-3 h-3" /> Regulamento oficial
          </a>
        )}
      </div>

      {/* ── Lista de inscritos (expandida) ── */}
      {registrantsOpen && (
        <div className="space-y-3">
          {/* Staleness warning */}
          {isStale(syncedAt) && (
            <div className="flex items-center gap-2 bg-status-closing/10 border border-status-closing/30 rounded-xl px-3 py-2 text-xs text-status-closing">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span className="flex-1">Dados com mais de {STALE_HOURS}h. Atualize para ver a lista mais recente.</span>
              <button onClick={handleRefreshRegistrants} className="shrink-0">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Sync info bar */}
          {(syncedAt || sourceLabel) && !registrantsLoading && (
            <div className="flex items-center gap-1.5 text-[11px] text-text-muted px-1">
              <RefreshCw className="w-3 h-3 shrink-0" />
              {sourceLabel && <span>Fonte: {sourceLabel}</span>}
              {sourceLabel && syncedAt && <span>·</span>}
              {syncedAt && <span>Atualizado em {fmtDateTime(syncedAt)}</span>}
            </div>
          )}

          {registrantsLoading && (
            <div className="card py-10 flex justify-center">
              <Loader2 className="w-6 h-6 text-accent-neon animate-spin" />
            </div>
          )}

          {!registrantsLoading && registrants && registrants.categories.length === 0 && (
            <div className="card text-center py-8 space-y-1">
              <Users className="w-8 h-8 text-text-muted mx-auto" />
              <p className="text-sm font-medium text-text-secondary">Lista ainda não publicada</p>
              <p className="text-xs text-text-muted">
                A federação ainda não divulgou as inscrições deste torneio.
                Tente novamente mais tarde ou consulte o site oficial.
              </p>
            </div>
          )}

          {!registrantsLoading && registrants && registrants.categories.length > 0 && (
            <>
              {groupCategories(registrants.categories).map(({ baseName, cats }) =>
                cats.length === 1 ? (
                  <RegistrantsCategoryCard
                    key={cats[0].category_text}
                    cat={cats[0]}
                    expanded={expandedCats.has(cats[0].category_text)}
                    onToggle={() => toggleCat(cats[0].category_text)}
                  />
                ) : (
                  <GroupedCategoryCard
                    key={baseName}
                    baseName={baseName}
                    cats={cats}
                    expandedCats={expandedCats}
                    onToggle={toggleCat}
                  />
                )
              )}

              {/* Note about ranking replacement */}
              <div className="card flex items-start gap-3 bg-accent-blue/5 border border-accent-blue/20">
                <Info className="w-4 h-4 text-accent-blue shrink-0 mt-0.5" />
                <p className="text-[11px] text-text-muted leading-relaxed">
                  O status "Confirmado na chave" indica que o atleta está confirmado conforme os dados publicados pela federação. Em torneios com critério de ranking, um atleta pago pode ser substituído se um atleta com ranking superior se inscrever após o preenchimento das vagas.
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Linha do Tempo ── */}
      {(ed.entry_open_at || ed.entry_close_at || ed.withdrawal_deadline_at || ed.start_date) && (
        <div className="card space-y-0">
          <h2 className="font-semibold mb-4">Linha do Tempo</h2>
          <TimelineItem
            icon={<LogIn className="w-3.5 h-3.5" />}
            label="Início das inscrições"
            value={ed.entry_open_at}
            color="text-accent-blue"
            dotColor="border-accent-blue bg-accent-blue/15"
          />
          <TimelineItem
            icon={<Lock className="w-3.5 h-3.5" />}
            label="Encerramento das inscrições"
            value={ed.entry_close_at}
            color="text-status-closing"
            dotColor="border-status-closing bg-status-closing/15"
          />
          {ed.withdrawal_deadline_at && (
            <TimelineItem
              icon={<DoorOpen className="w-3.5 h-3.5" />}
              label="Limite para desistência"
              value={ed.withdrawal_deadline_at}
              color="text-status-canceled"
              dotColor="border-status-canceled bg-status-canceled/15"
            />
          )}
          <TimelineItem
            icon={<Trophy className="w-3.5 h-3.5" />}
            label="Início do torneio"
            value={ed.start_date}
            color="text-accent-neon"
            dotColor="border-accent-neon bg-accent-neon/15"
            isLast
          />
        </div>
      )}

      {/* ── Minha inscrição ── */}
      {myReg && (
        <div className="card space-y-3">
          <div className="flex items-center gap-2">
            {myReg.registration_status === 'confirmed'
              ? <CheckCircle className="w-5 h-5 text-accent-neon" />
              : myReg.registration_status === 'waiting_list'
              ? <Clock className="w-5 h-5 text-status-closing" />
              : myReg.registration_status === 'pending_payment'
              ? <CreditCard className="w-5 h-5 text-accent-blue" />
              : <XCircle className="w-5 h-5 text-text-muted" />}
            <span className={`font-bold text-sm ${
              myReg.registration_status === 'confirmed' ? 'text-accent-neon'
              : myReg.registration_status === 'waiting_list' ? 'text-status-closing'
              : myReg.registration_status === 'pending_payment' ? 'text-accent-blue'
              : 'text-text-muted'
            }`}>
              {myReg.registration_status_label}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {myReg.slot_position != null && (
              <div className="bg-bg-base rounded-xl p-3 text-center border border-border-subtle">
                <p className="text-[10px] text-text-muted">Posição</p>
                <p className={`text-2xl font-bold mt-1 ${myReg.in_draw ? 'text-accent-neon' : 'text-text-primary'}`}>
                  #{myReg.slot_position}
                </p>
                {myReg.max_participants && (
                  <p className={`text-[10px] mt-0.5 font-semibold ${myReg.in_draw ? 'text-accent-neon' : 'text-status-canceled'}`}>
                    {myReg.in_draw ? 'Na chave' : `Fora (limite ${myReg.max_participants})`}
                  </p>
                )}
              </div>
            )}
            <div className="bg-bg-base rounded-xl p-3 text-center border border-border-subtle">
              <p className="text-[10px] text-text-muted">Pagamento</p>
              {myReg.payment_status === 'paid' || myReg.payment_status === 'waived'
                ? <CheckCircle className="w-6 h-6 text-accent-neon mx-auto my-1" />
                : <Clock className="w-6 h-6 text-status-closing mx-auto my-1" />}
              <p className={`text-[10px] font-semibold ${myReg.payment_status === 'paid' || myReg.payment_status === 'waived' ? 'text-accent-neon' : 'text-status-closing'}`}>
                {myReg.payment_status_label}
              </p>
            </div>
            {myReg.category_text && (
              <div className="bg-bg-base rounded-xl p-3 text-center border border-border-subtle">
                <p className="text-[10px] text-text-muted">Categoria</p>
                <p className="text-xs font-semibold mt-1">{myReg.category_text}</p>
              </div>
            )}
          </div>
          <button
            onClick={handleWithdraw}
            disabled={withdrawing}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-status-canceled/50 text-status-canceled text-sm font-semibold hover:bg-status-canceled/10 transition-colors disabled:opacity-50"
          >
            {withdrawing ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserX className="w-4 h-4" />}
            Cancelar minha inscrição
          </button>
        </div>
      )}

      {/* ── Categorias ── */}
      <div className="card">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          Categorias
          {elig && (
            <span className="text-xs text-text-muted font-normal">
              {elig.total_count} no total — {elig.compatible_count} compatíveis com você
            </span>
          )}
        </h2>

        {(!elig || elig.total_count === 0) && ed.categories.length > 0 && (
          <div className="space-y-2">
            {ed.categories.map((c) => (
              <div key={c.id} className="flex items-center justify-between text-sm gap-2">
                <div className="flex flex-col min-w-0">
                  <span>{c.source_category_text}</span>
                  {c.notes && (
                    <span className="text-[11px] text-text-muted">{c.notes}</span>
                  )}
                </div>
                {c.price_brl && <span className="text-text-muted shrink-0">{fmtBRL(c.price_brl)}</span>}
              </div>
            ))}
            {!profile && (
              <p className="text-xs text-text-muted pt-2">
                <Link to="/perfil" className="text-accent-neon hover:underline">
                  Configure seu perfil
                </Link>{' '}
                para ver quais categorias são compatíveis com você.
              </p>
            )}
          </div>
        )}

        {elig && elig.total_count > 0 && (
          <div className="space-y-3">
            {compatCats.length > 0 && (
              <CategoryGroup title="Compatíveis com você" color="text-accent-neon"
                icon={<CheckCircle2 className="w-4 h-4" />} items={compatCats} />
            )}
            {unknownCats.length > 0 && (
              <CategoryGroup title="Indeterminadas" color="text-text-secondary"
                icon={<HelpCircle className="w-4 h-4" />} items={unknownCats} subdued />
            )}
            {incompatCats.length > 0 && (
              <CategoryGroup title="Outras categorias" color="text-text-muted"
                icon={<XCircle className="w-4 h-4" />} items={incompatCats} subdued />
            )}
          </div>
        )}

        {ed.categories.length === 0 && (
          <p className="text-sm text-text-muted">
            Nenhuma categoria listada pela fonte. Consulte o regulamento oficial.
          </p>
        )}
      </div>

      {/* ── Origem dos dados ── */}
      <div className="card">
        <h2 className="font-semibold mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" /> Origem dos dados
        </h2>
        <dl className="text-xs space-y-1 text-text-secondary">
          <div className="flex justify-between">
            <dt>Fonte</dt>
            <dd className="text-text-primary">{ed.source_name || '—'}</dd>
          </div>
          {ed.official_source_url && (
            <div className="flex justify-between items-center">
              <dt>Link oficial</dt>
              <dd>
                <a href={ed.official_source_url} target="_blank" rel="noopener noreferrer"
                  className="text-accent-blue hover:underline truncate max-w-[180px] inline-block">
                  {new URL(ed.official_source_url).hostname}
                </a>
              </dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt>Última atualização</dt>
            <dd className="text-text-primary">{ed.fetched_at ? fmtRelative(ed.fetched_at) : '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Confiança dos dados</dt>
            <dd className={`font-medium ${
              ed.data_confidence === 'high' ? 'text-accent-neon'
              : ed.data_confidence === 'low' ? 'text-status-canceled'
              : 'text-status-closing'
            }`}>
              {ed.data_confidence === 'high' ? 'Alta'
                : ed.data_confidence === 'low' ? 'Baixa' : 'Média'}
            </dd>
          </div>
        </dl>
      </div>

      {/* ── Histórico de alterações ── */}
      {ed.change_events && ed.change_events.length > 0 && (
        <div className="card">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <History className="w-4 h-4" /> Histórico de alterações
          </h2>
          <ol className="space-y-2 text-xs">
            {ed.change_events.slice(0, 8).map((e) => (
              <li key={e.id} className="border-l-2 border-border-subtle pl-3 py-1">
                <div className="text-text-primary font-medium">{formatChangeEventTitle(e.event_type)}</div>
                <div className="text-text-muted">{fmtRelative(e.detected_at)}</div>
                <div className="text-[11px] text-text-secondary mt-1 space-y-1">
                  {formatChangeEventDetails(e).map((line) => (
                    <div key={`${e.id}-${line}`}>{line}</div>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
};

// ── Timeline item ─────────────────────────────────────────────────────────────

function fmtDateMaybeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return iso.includes('T') ? fmtDateTime(iso) : fmtDate(iso);
}

function TimelineItem({
  icon, label, value, color, dotColor, isLast = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null | undefined;
  color: string;
  dotColor: string;
  isLast?: boolean;
}) {
  const hasValue = !!value;
  return (
    <div className="flex gap-3" style={{ marginBottom: isLast ? 0 : 20 }}>
      {/* Dot + line */}
      <div className="flex flex-col items-center w-8 shrink-0">
        <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center ${hasValue ? dotColor : 'border-text-muted/30 bg-text-muted/10'} ${hasValue ? color : 'text-text-muted'}`}>
          {icon}
        </div>
        {!isLast && (
          <div className="w-0.5 flex-1 bg-border-subtle mt-1" />
        )}
      </div>
      {/* Content */}
      <div className="pt-1 pb-1">
        <p className="text-[11px] text-text-muted">{label}</p>
        <p className={`text-sm font-semibold mt-0.5 ${hasValue ? 'text-text-primary' : 'text-text-muted'}`}>
          {fmtDateMaybeTime(value)}
        </p>
      </div>
    </div>
  );
}

// ── Registrants: category card ────────────────────────────────────────────────

// ── Category grouping ────────────────────────────────────────────────────────

const VARIANT_RE = /\s*\((GA|G1\+?|G2\+?|G3\+?|[A-Z]\d*\+?)\)\s*$/i;

function groupCategories(categories: RegistrantCategory[]) {
  const groups = new Map<string, RegistrantCategory[]>();
  for (const cat of categories) {
    const base = cat.category_text.replace(VARIANT_RE, '').trim();
    if (!groups.has(base)) groups.set(base, []);
    groups.get(base)!.push(cat);
  }
  return Array.from(groups.entries()).map(([baseName, cats]) => ({ baseName, cats }));
}

function variantLabel(text: string): string {
  const m = text.match(VARIANT_RE);
  return m ? m[1] : text;
}

// ── Grouped category: multiple variants (GA, G1+) side by side ───────────────

function GroupedCategoryCard({
  baseName, cats, expandedCats, onToggle,
}: {
  baseName: string;
  cats: RegistrantCategory[];
  expandedCats: Set<string>;
  onToggle: (key: string) => void;
}) {
  const activeCat = cats.find((c) => expandedCats.has(c.category_text)) ?? null;

  return (
    <div className="card p-0 overflow-hidden">
      {/* Base name header */}
      <div className="px-4 pt-4 pb-2">
        <p className="font-semibold text-sm">{baseName}</p>
      </div>

      {/* Variant chips side by side */}
      <div className="flex gap-2 px-4 pb-3 overflow-x-auto scrollbar-none">
        {cats.map((cat) => {
          const isActive = expandedCats.has(cat.category_text);
          const label = variantLabel(cat.category_text);
          const total = cat.summary.total;
          const inDraw = cat.summary.in_draw;
          return (
            <button
              key={cat.category_text}
              onClick={() => onToggle(cat.category_text)}
              className={`shrink-0 flex flex-col items-center gap-0.5 px-4 py-2.5 rounded-xl border transition-colors text-xs font-semibold ${
                isActive
                  ? 'bg-accent-neon text-bg-base border-accent-neon'
                  : 'bg-bg-elevated border-border-subtle text-text-secondary hover:border-accent-neon/50'
              }`}
            >
              <span className="text-sm font-bold">{label}</span>
              <span className={`font-normal ${isActive ? 'text-bg-base/70' : 'text-text-muted'}`}>
                {inDraw} na chave · {total} inscritos
              </span>
            </button>
          );
        })}
      </div>

      {/* Expanded variant entries */}
      {activeCat && (
        <>
          {/* Summary pills for active variant */}
          <div className="flex flex-wrap gap-1.5 px-4 pb-3">
            {[
              { label: `${activeCat.summary.total} inscritos`, cls: 'text-text-muted border-text-muted/30 bg-text-muted/10' },
              { label: `${activeCat.summary.in_draw} na chave`, cls: 'text-accent-neon border-accent-neon/30 bg-accent-neon/10' },
              { label: `${activeCat.summary.paid} pagos`, cls: 'text-accent-blue border-accent-blue/30 bg-accent-blue/10' },
              { label: `${activeCat.summary.pending} pendentes`, cls: 'text-status-closing border-status-closing/30 bg-status-closing/10' },
            ].map((p) => (
              <span key={p.label} className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${p.cls}`}>
                {p.label}
              </span>
            ))}
          </div>
          <div className="border-t border-border-subtle">
            {activeCat.entries.map((entry) => (
              <EntryRow key={entry.id} entry={entry} maxP={activeCat.summary.total_slots ?? activeCat.max_participants} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function RegistrantsCategoryCard({
  cat, expanded, onToggle,
}: {
  cat: RegistrantCategory;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { summary } = cat;
  const totalSlots = summary.total_slots ?? cat.max_participants;
  const drawFull = totalSlots != null && summary.filled_slots >= totalSlots;
  const isCosatSource = cat.entries[0]?.source === 'cosat';

  const pills = isCosatSource
    ? [{ label: `${summary.total} inscrito${summary.total !== 1 ? 's' : ''}`, cls: 'text-text-muted border-text-muted/30 bg-text-muted/10' },
       { label: 'Pagamento não informado pela fonte', cls: 'text-text-muted border-text-muted/20 bg-transparent italic' }]
    : [
        { label: `${summary.total} inscrito${summary.total !== 1 ? 's' : ''}`,            cls: 'text-text-muted border-text-muted/30 bg-text-muted/10' },
        { label: `${summary.in_draw} na chave`,                                            cls: 'text-accent-neon border-accent-neon/30 bg-accent-neon/10' },
        { label: `${summary.paid} pago${summary.paid !== 1 ? 's' : ''}`,                  cls: 'text-accent-blue border-accent-blue/30 bg-accent-blue/10' },
        { label: `${summary.pending} pendente${summary.pending !== 1 ? 's' : ''}`,         cls: 'text-status-closing border-status-closing/30 bg-status-closing/10' },
      ];

  return (
    <div className="card p-0 overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 text-left"
      >
        <div>
          <p className="font-semibold text-sm">{cat.category_text}</p>
          {totalSlots != null && (
            <p className="text-xs text-text-muted mt-0.5">
              Vagas: {summary.filled_slots}/{totalSlots}
              {drawFull
                ? ' · Chave completa'
                : ` · ${summary.remaining_slots ?? (totalSlots - summary.filled_slots)} restante${(summary.remaining_slots ?? 1) !== 1 ? 's' : ''}`}
            </p>
          )}
        </div>
        {expanded
          ? <ChevronUp className="w-4 h-4 text-text-muted shrink-0" />
          : <ChevronDown className="w-4 h-4 text-text-muted shrink-0" />}
      </button>

      {/* Summary pills */}
      <div className="flex flex-wrap gap-1.5 px-4 pb-3">
        {pills.map((p) => (
          <span key={p.label} className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${p.cls}`}>
            {p.label}
          </span>
        ))}
      </div>

      {/* Entry list */}
      {expanded && (
        <div className="border-t border-border-subtle">
          {cat.entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} maxP={totalSlots} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Registrants: entry row ────────────────────────────────────────────────────

function EntryRow({ entry, maxP }: { entry: FederationEntryItem; maxP: number | null }) {
  const sc = STATUS_CONFIG[entry.status] ?? {
    icon: <HelpCircle className="w-3.5 h-3.5" />,
    color: 'text-text-muted',
    label: entry.status_label || 'Desconhecido',
  };
  const payColor = PAYMENT_COLOR[entry.payment_status] ?? 'text-text-muted';
  const confCfg = CONFIDENCE_CONFIG[entry.confidence] ?? CONFIDENCE_CONFIG.medium;
  const isRemoved = entry.status === 'removed';
  const showPayment = entry.source !== 'cosat' && entry.status !== 'registered';

  return (
    <div className={`flex items-start gap-3 px-4 py-3 border-b border-border-subtle last:border-0 ${isRemoved ? 'opacity-60' : ''}`}>
      {/* Slot # */}
      <div className="w-8 text-right shrink-0 pt-0.5">
        <span className={`text-sm font-bold ${isRemoved ? sc.color : entry.in_draw ? 'text-accent-neon' : 'text-text-muted'}`}>
          {entry.slot_position != null ? `#${entry.slot_position}` : '—'}
        </span>
      </div>

      {/* Player info */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold ${isRemoved ? 'line-through' : ''}`}>
          {entry.player_name}
          {entry.player_country_code && entry.player_country_code !== 'BRA' && (
            <span className="ml-1 text-[10px] text-text-muted font-normal">({entry.player_country_code})</span>
          )}
        </p>
        {entry.player_country_name && entry.player_country_code !== 'BRA' && (
          <p className="text-[11px] text-text-muted">{entry.player_country_name}</p>
        )}
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {entry.ranking_position != null && (
            <span className="text-[11px] text-text-muted">Ranking {entry.ranking_position}</span>
          )}
          {entry.notes && (
            <span className="text-[11px] text-text-muted">· {entry.notes}</span>
          )}
        </div>
        {isRemoved && (
          <p className="text-[11px] mt-1 leading-4" style={{ color: 'var(--color-status-canceled)' }}>
            {entry.replacement_reason || 'Removido por critério de ranking da federação'}
          </p>
        )}
        {entry.source_url && (
          <a
            href={entry.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 mt-1 text-[10px] text-accent-blue hover:underline"
          >
            <ExternalLink className="w-2.5 h-2.5" /> Ver na fonte oficial
          </a>
        )}
      </div>

      {/* Status + payment + confidence */}
      <div className="flex flex-col items-end gap-1 shrink-0">
        <div className={`flex items-center gap-1 ${sc.color}`}>
          {sc.icon}
          <span className="text-[10px] font-semibold">{sc.label}</span>
        </div>
        {showPayment && (
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-current/10 ${payColor}`}>
            {entry.payment_status_label}
          </span>
        )}
        <div className={`flex items-center gap-0.5 ${confCfg.color}`}>
          {confCfg.icon}
          <span className="text-[9px]">{confCfg.label}</span>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

const Stat: React.FC<{ icon: React.ReactNode; label: string; value: string; accent?: boolean }> = (
  { icon, label, value, accent = false }
) => (
  <div>
    <div className="text-[10px] text-text-muted uppercase tracking-wider flex items-center gap-1">
      {icon} {label}
    </div>
    <div className={`text-sm mt-0.5 font-medium ${accent ? 'text-accent-neon' : ''}`}>
      {value}
    </div>
  </div>
);

const CategoryGroup: React.FC<{
  title: string;
  color: string;
  icon: React.ReactNode;
  items: EditionEligibility['categories'];
  subdued?: boolean;
}> = ({ title, color, icon, items, subdued = false }) => (
  <div>
    <div className={`text-xs font-semibold mb-2 flex items-center gap-1 ${color}`}>
      {icon} {title} ({items.length})
    </div>
    <div className="space-y-1">
      {items.map((c) => (
        <div
          key={c.tournament_category_id}
          className={`flex items-start justify-between gap-2 p-2 rounded-lg ${
            subdued ? 'bg-bg-subtle/40' : 'bg-accent-neon/5 border border-accent-neon/20'
          }`}
        >
          <div className="min-w-0">
            <div className={`text-sm font-medium ${subdued ? 'text-text-secondary' : 'text-text-primary'}`}>
              {c.source_text}
            </div>
            {c.result.reasons.length > 0 && (
              <div className="text-[10px] text-text-muted mt-0.5">
                {c.result.reasons.map((r) => translateReason(r)).join(' • ')}
              </div>
            )}
            {c.result.ranking_check && c.result.ranking_check !== 'not_applicable' && (
              <div className={`text-[10px] mt-0.5 ${
                c.result.ranking_check === 'within_cutoff' ? 'text-accent-neon'
                : c.result.ranking_check === 'beyond_cutoff' ? 'text-amber-400'
                : 'text-text-muted italic'
              }`}>
                {c.result.ranking_check === 'within_cutoff' && '✓ Ranking dentro do corte estimado.'}
                {c.result.ranking_check === 'beyond_cutoff' && '⚠ Ranking acima do corte estimado — vaga incerta. Confirme na fonte oficial.'}
                {c.result.ranking_check === 'unknown' && (c.result.ranking_note || 'Corte de ranking não estimado.')}
              </div>
            )}
          </div>
          {c.price_brl && (
            <span className="text-xs text-text-muted whitespace-nowrap">{fmtBRL(c.price_brl)}</span>
          )}
        </div>
      ))}
    </div>
  </div>
);

