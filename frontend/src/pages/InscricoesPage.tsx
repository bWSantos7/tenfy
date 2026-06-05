import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, CheckCircle, ChevronRight, Ticket, User, Calendar, Trophy, XCircle, AlertCircle, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { TournamentRegistration, WatchlistItem, ParentChild } from '../types';
import { myRegistrations, withdrawRegistration } from '../services/registrations';
import { listChildren, listChildWatchlist, listWatchlist } from '../services/data';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { fmtDateRange } from '../utils/format';

interface ChildGroup {
  childName: string;
  childId: number;
  items: WatchlistItem[];
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  confirmed:       { label: 'Confirmado',       color: 'text-status-open',    bg: 'bg-status-open/15'   },
  waiting_list:    { label: 'Lista de espera',  color: 'text-status-closing', bg: 'bg-status-closing/15' },
  pending_payment: { label: 'Pag. pendente',    color: 'text-accent-blue',    bg: 'bg-accent-blue/15'   },
  expired:         { label: 'Não confirmada',   color: 'text-status-canceled', bg: 'bg-status-canceled/15' },
  withdrawn:       { label: 'Cancelado',        color: 'text-status-canceled', bg: 'bg-status-canceled/15' },
};

const PAYMENT_META: Record<string, { label: string; color: string }> = {
  paid:     { label: 'Pago',       color: 'text-status-open'    },
  waived:   { label: 'Isento',     color: 'text-status-open'    },
  pending:  { label: 'Pendente',   color: 'text-status-closing' },
  refunded: { label: 'Estornado',  color: 'text-status-canceled' },
  unknown:  { label: 'Não inf.',   color: 'text-text-muted'     },
};

export const InscricoesPage: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [childGroups, setChildGroups] = useState<ChildGroup[]>([]);
  const [withdrawing, setWithdrawing] = useState<number | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState<number | null>(null);
  // Watchlist-only desistências (sem inscrição oficial) — exibidas no Histórico
  // para manter o mesmo status da Agenda e do Detalhe do Torneio.
  const [declaredWithdrawn, setDeclaredWithdrawn] = useState<WatchlistItem[]>([]);

  async function load() {
    setLoading(true);
    try {
      const regs = await myRegistrations().catch(() => [] as TournamentRegistration[]);
      setRegistrations(regs);

      if (user?.role === 'parent') {
        const children = await listChildren().catch(() => [] as ParentChild[]);
        const childWatchlists = await Promise.all(
          children.map((link) => listChildWatchlist(link.child).catch(() => [] as WatchlistItem[])),
        );
        const groups: ChildGroup[] = children
          .map((link, i) => ({
            childName: link.child_detail.full_name || link.child_detail.email,
            childId: link.child,
            // Include 'completed' — backend sets this automatically when a result is saved
            items: childWatchlists[i].filter((it) => it.user_status === 'registered_declared' || it.user_status === 'completed'),
          }))
          .filter((g) => g.items.length > 0);
        setChildGroups(groups);
        setDeclaredWithdrawn(childWatchlists.flat().filter((it) => it.user_status === 'withdrawn'));
      } else {
        const wl = await listWatchlist().catch(() => [] as WatchlistItem[]);
        // Include 'completed' — backend sets this automatically when a result is saved
        const inscribed = wl.filter((i) => i.user_status === 'registered_declared' || i.user_status === 'completed');
        setChildGroups(inscribed.length > 0 ? [{ childName: '', childId: 0, items: inscribed }] : []);
        setDeclaredWithdrawn(wl.filter((i) => i.user_status === 'withdrawn'));
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    window.addEventListener('registration-withdrawn', load);
    return () => window.removeEventListener('registration-withdrawn', load);
  }, [user?.role]);

  async function handleWithdraw(regId: number) {
    setWithdrawing(regId);
    try {
      await withdrawRegistration(regId);
      toast.success('Inscrição cancelada.');
      await load();
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setWithdrawing(null);
      setConfirmWithdraw(null);
    }
  }

  // Inscrições ativas = não cancelada, torneio não passado E não expirada.
  // Torneios já finalizados/cancelados e inscrições não confirmadas (aguardando
  // pagamento após o prazo) vão para o Histórico, mesmo sem cancelamento manual.
  const activeRegs = registrations.filter((r) => !r.is_withdrawn && !r.is_past && r.registration_status !== 'expired');
  const withdrawnRegs = registrations.filter((r) => r.is_withdrawn || r.is_past || r.registration_status === 'expired');

  // Uma inscrição declarada cujo torneio já passou (finalizado/cancelado ou
  // data final no passado) vai para o Histórico, não fica em "declaradas ativas".
  const todayStr = new Date().toISOString().slice(0, 10);
  const isDeclaredPast = (item: WatchlistItem): boolean => {
    if (item.user_status === 'completed') return true;
    const ed = item.edition_detail;
    if (!ed) return false;
    const ds = ed.dynamic_status || ed.status;
    if (ds === 'finished' || ds === 'canceled') return true;
    return !!(ed.end_date && ed.end_date < todayStr);
  };
  const activeChildGroups = childGroups
    .map((g) => ({ ...g, items: g.items.filter((it) => !isDeclaredPast(it)) }))
    .filter((g) => g.items.length > 0);
  const pastDeclared = childGroups.flatMap((g) => g.items.filter(isDeclaredPast));
  const totalDeclared = activeChildGroups.reduce((acc, g) => acc + g.items.length, 0);

  // Avoid showing a desistência twice when both an official registration and a
  // watchlist declaration exist for the same edition.
  const withdrawnRegEditionIds = new Set(withdrawnRegs.map((r) => r.edition_id));
  const declaredWithdrawnOnly = declaredWithdrawn.filter(
    (it) => !withdrawnRegEditionIds.has(it.edition_detail?.id),
  );
  const hasAnything =
    totalDeclared > 0 || activeRegs.length > 0 || withdrawnRegs.length > 0 ||
    declaredWithdrawnOnly.length > 0 || pastDeclared.length > 0;

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
        <h1 className="text-2xl font-bold">Minhas Inscrições</h1>
        <p className="text-sm text-text-muted">Inscrições oficiais e declaradas por você</p>
      </div>

      {/* Banner informativo sobre sincronização oficial */}
      <div className="flex items-start gap-2.5 bg-accent-blue/8 border border-accent-blue/25 rounded-xl px-3 py-2.5">
        <AlertCircle className="w-4 h-4 text-accent-blue mt-0.5 shrink-0" />
        <p className="text-xs text-text-secondary leading-relaxed">
          <span className="font-semibold text-accent-blue">Reconhecimento automático em desenvolvimento.</span>{' '}
          Inscrições marcadas como "declaradas" foram informadas por você. Inscrições "oficiais" foram importadas da fonte do torneio quando disponível.
        </p>
      </div>

      {!hasAnything ? (
        <div className="card text-center py-12 space-y-3">
          <Ticket className="w-10 h-10 text-text-muted mx-auto" />
          <p className="font-semibold">Nenhuma inscrição ainda</p>
          <p className="text-sm text-text-secondary">Na Agenda, marque um torneio como "Inscrito" para acompanhar aqui.</p>
          <Link to="/watchlist" className="btn-primary inline-flex items-center gap-2 !text-sm">
            Ir para Agenda
          </Link>
        </div>
      ) : (
        <>
          {/* ─── Inscrições declaradas (watchlist) ───────────────────────── */}
          {activeChildGroups.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 text-text-muted" />
                  <h2 className="font-bold text-sm">Inscrições declaradas por você</h2>
                </div>
                <span className="text-xs text-text-muted">{totalDeclared}</span>
              </div>

              {activeChildGroups.map((group) => (
                <div key={group.childId || 'self'} className="space-y-2">
                  {user?.role === 'parent' && (
                    <div className="flex items-center gap-1.5 px-1 mt-2">
                      <User className="w-3.5 h-3.5 text-accent-blue" />
                      <span className="text-xs font-bold text-accent-blue">{group.childName}</span>
                    </div>
                  )}
                  {group.items.map((item) => {
                    const ed = item.edition_detail;
                    const officiallyConfirmed = item.is_registered;
                    return (
                      <Link key={`wl-${item.id}`} to={`/torneios/${ed.id}`} className="card flex items-center gap-3 hover:border-accent-neon/30 transition-colors no-underline">
                        <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${officiallyConfirmed ? 'bg-status-open/15' : 'bg-accent-neon/15'}`}>
                          <CheckCircle className={`w-5 h-5 ${officiallyConfirmed ? 'text-status-open' : 'text-accent-neon'}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-bold text-sm line-clamp-1">{ed.title}</div>
                          {ed.start_date && (
                            <div className="text-xs text-text-muted mt-0.5">
                              {fmtDateRange(ed.start_date, ed.end_date)}
                            </div>
                          )}
                          {officiallyConfirmed ? (
                            <span className="inline-flex items-center gap-1 mt-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-status-open/15 text-status-open">
                              <ShieldCheck className="w-3 h-3" />
                              Inscrição Confirmada
                            </span>
                          ) : (
                            <span className="inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-text-muted/15 text-text-muted">Declarado Manualmente</span>
                          )}
                        </div>
                        <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          )}

          {/* ─── Inscrições oficiais (backend) ───────────────────────────── */}
          {activeRegs.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-status-open" />
                  <h2 className="font-bold text-sm">Inscrições oficiais</h2>
                </div>
                <span className="text-xs text-text-muted">{activeRegs.length}</span>
              </div>
              {activeRegs.map((reg) => (
                <RegistrationCard
                  key={reg.id}
                  reg={reg}
                  confirmWithdraw={confirmWithdraw}
                  withdrawing={withdrawing}
                  onConfirmWithdraw={setConfirmWithdraw}
                  onWithdraw={handleWithdraw}
                />
              ))}
            </div>
          )}

          {/* ─── Histórico ───────────────────────────────────────────────── */}
          {(withdrawnRegs.length > 0 || declaredWithdrawnOnly.length > 0 || pastDeclared.length > 0) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-sm text-text-muted">Histórico</h2>
                <span className="text-xs text-text-muted">Encerradas e canceladas</span>
              </div>
              {withdrawnRegs.map((reg) => (
                <RegistrationCard key={reg.id} reg={reg} confirmWithdraw={null} withdrawing={null} />
              ))}
              {pastDeclared.map((item) => {
                const ed = item.edition_detail;
                return (
                  <Link key={`wlp-${item.id}`} to={`/torneios/${ed.id}`} className="card flex items-center gap-3 hover:border-accent-neon/30 transition-colors no-underline opacity-80">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-status-finished/15">
                      <CheckCircle className="w-5 h-5 text-status-finished" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-sm line-clamp-1">{ed.title}</div>
                      {ed.start_date && (
                        <div className="text-xs text-text-muted mt-0.5">{fmtDateRange(ed.start_date, ed.end_date)}</div>
                      )}
                      <span className="inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-status-finished/15 text-status-finished">
                        {item.user_status === 'completed' ? 'Concluído' : 'Encerrado'}
                      </span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />
                  </Link>
                );
              })}
              {declaredWithdrawnOnly.map((item) => {
                const ed = item.edition_detail;
                return (
                  <Link key={`wlw-${item.id}`} to={`/torneios/${ed.id}`} className="card flex items-center gap-3 hover:border-status-canceled/30 transition-colors no-underline opacity-80">
                    <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-status-canceled/15">
                      <XCircle className="w-5 h-5 text-status-canceled" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-sm line-clamp-1">{ed.title}</div>
                      {ed.start_date && (
                        <div className="text-xs text-text-muted mt-0.5">{fmtDateRange(ed.start_date, ed.end_date)}</div>
                      )}
                      <span className="inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-status-canceled/15 text-status-canceled">Desistiu</span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />
                  </Link>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};

function RegistrationCard({
  reg, confirmWithdraw, withdrawing, onConfirmWithdraw, onWithdraw,
}: {
  reg: TournamentRegistration;
  confirmWithdraw: number | null;
  withdrawing: number | null;
  onConfirmWithdraw?: (id: number | null) => void;
  onWithdraw?: (id: number) => void;
}) {
  const sc = STATUS_META[reg.registration_status] ?? STATUS_META['pending_payment'];
  const pc = PAYMENT_META[reg.payment_status] ?? PAYMENT_META['unknown'];

  return (
    <div className="card space-y-3">
      {/* Header: título + badge de status */}
      <div className="flex items-start justify-between gap-2">
        <Link to={`/torneios/${reg.edition_id}`} className="font-bold text-sm hover:text-accent-neon transition-colors line-clamp-2 flex-1">
          {reg.edition_title}
        </Link>
        <span className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-md ${sc.bg} ${sc.color}`}>
          {sc.label}
        </span>
      </div>

      {/* Datas + categoria */}
      <div className="space-y-1">
        {reg.edition_start_date && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Calendar className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span>{fmtDateRange(reg.edition_start_date, reg.edition_end_date)}</span>
          </div>
        )}
        {reg.category_text && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Trophy className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span>{reg.category_text}</span>
          </div>
        )}
      </div>

      {/* Stats: posição / ranking / pagamento */}
      {!reg.is_withdrawn && (
        <div className="grid grid-cols-3 gap-2">
          {reg.slot_position != null && (
            <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
              <div className="text-[10px] text-text-muted mb-0.5">Posição</div>
              <div className={`font-bold text-base ${reg.in_draw ? 'text-accent-neon' : 'text-text-primary'}`}>
                #{reg.slot_position}
              </div>
              {reg.max_participants && (
                <div className={`text-[9px] ${reg.in_draw ? 'text-accent-neon' : 'text-red-400'}`}>
                  {reg.in_draw ? `na chave (${reg.max_participants})` : `fora (lim. ${reg.max_participants})`}
                </div>
              )}
            </div>
          )}
          {reg.ranking_position != null && (
            <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
              <div className="text-[10px] text-text-muted mb-0.5">Ranking</div>
              <div className="font-bold text-base">{reg.ranking_position}º</div>
            </div>
          )}
          <div className="bg-bg-elevated rounded-xl p-2.5 text-center border border-border-subtle">
            <div className="text-[10px] text-text-muted mb-0.5">Pagamento</div>
            <div className={`text-xs font-bold ${pc.color}`}>{pc.label}</div>
          </div>
        </div>
      )}

      {/* Botão cancelar inscrição */}
      {!reg.is_withdrawn && onWithdraw && onConfirmWithdraw && (
        confirmWithdraw === reg.id ? (
          <div className="flex gap-2">
            <button className="flex-1 py-2 rounded-xl text-xs font-bold bg-red-500/15 border border-red-500/40 text-red-400 hover:bg-red-500/25"
              onClick={() => onWithdraw(reg.id)} disabled={withdrawing === reg.id}>
              {withdrawing === reg.id ? <Loader2 className="w-3.5 h-3.5 animate-spin mx-auto" /> : 'Confirmar cancelamento'}
            </button>
            <button className="flex-1 py-2 rounded-xl text-xs font-bold bg-bg-elevated text-text-muted hover:text-text-primary"
              onClick={() => onConfirmWithdraw(null)}>
              Manter inscrição
            </button>
          </div>
        ) : (
          <button className="w-full py-2 rounded-xl text-xs font-bold border border-border-subtle text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors"
            onClick={() => onConfirmWithdraw(reg.id)}>
            Cancelar inscrição
          </button>
        )
      )}

      {/* Status cancelado */}
      {reg.is_withdrawn && (
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <XCircle className="w-3.5 h-3.5" />
          <span>Inscrição cancelada</span>
        </div>
      )}
    </div>
  );
}
