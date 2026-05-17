import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, CheckCircle, ChevronRight, Ticket, User, Calendar, Trophy, CreditCard, XCircle, Clock } from 'lucide-react';
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
            items: childWatchlists[i].filter((it) => it.user_status === 'registered_declared'),
          }))
          .filter((g) => g.items.length > 0);
        setChildGroups(groups);
      } else {
        const wl = await listWatchlist().catch(() => [] as WatchlistItem[]);
        const inscribed = wl.filter((i) => i.user_status === 'registered_declared');
        setChildGroups(inscribed.length > 0 ? [{ childName: '', childId: 0, items: inscribed }] : []);
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

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

  const activeRegs = registrations.filter((r) => !r.is_withdrawn);
  const withdrawnRegs = registrations.filter((r) => r.is_withdrawn);
  const totalDeclared = childGroups.reduce((acc, g) => acc + g.items.length, 0);
  const hasAnything = totalDeclared > 0 || activeRegs.length > 0 || withdrawnRegs.length > 0;

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
        <p className="text-sm text-text-muted">Torneios em que você declarou inscrição</p>
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
          {childGroups.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-sm">Inscrições declaradas</h2>
                <span className="text-xs text-text-muted">{totalDeclared} torneio{totalDeclared !== 1 ? 's' : ''}</span>
              </div>

              {childGroups.map((group) => (
                <div key={group.childId || 'self'} className="space-y-2">
                  {user?.role === 'parent' && (
                    <div className="flex items-center gap-1.5 px-1 mt-2">
                      <User className="w-3.5 h-3.5 text-accent-blue" />
                      <span className="text-xs font-bold text-accent-blue">{group.childName}</span>
                    </div>
                  )}
                  {group.items.map((item) => {
                    const ed = item.edition_detail;
                    return (
                      <Link key={`wl-${item.id}`} to={`/torneios/${ed.id}`} className="card flex items-center gap-3 hover:border-accent-neon/30 transition-colors no-underline">
                        <div className="w-9 h-9 rounded-full bg-accent-neon/15 flex items-center justify-center shrink-0">
                          <CheckCircle className="w-5 h-5 text-accent-neon" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-bold text-sm line-clamp-1">{ed.title}</div>
                          {ed.start_date && (
                            <div className="text-xs text-text-muted mt-0.5">
                              {fmtDateRange(ed.start_date, ed.end_date)}
                            </div>
                          )}
                          <span className="inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-accent-neon/15 text-accent-neon">Inscrito</span>
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
                <h2 className="font-bold text-sm">Inscrições oficiais</h2>
                <span className="text-xs text-text-muted">{activeRegs.length} inscrição{activeRegs.length !== 1 ? 'ões' : ''}</span>
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
          {withdrawnRegs.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-sm text-text-muted">Histórico</h2>
                <span className="text-xs text-text-muted">Canceladas</span>
              </div>
              {withdrawnRegs.map((reg) => (
                <RegistrationCard key={reg.id} reg={reg} confirmWithdraw={null} withdrawing={null} />
              ))}
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
