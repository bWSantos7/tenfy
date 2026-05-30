import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bell, BellOff, BellRing, Loader2, CheckCheck, Clock, AlertCircle, Sparkles, XCircle, ExternalLink, Users,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { Alert } from '../types';
import { listAlerts, markAlertRead, markAllAlertsRead, respondDependentInvite } from '../services/data';
import { fmtRelative } from '../utils/format';
import { extractApiError } from '../services/api';
import { usePushNotifications } from '../hooks/usePushNotifications';

const KIND_ICONS: Record<Alert['kind'], React.ReactNode> = {
  deadline: <Clock className="w-5 h-5 text-status-closing" />,
  change: <AlertCircle className="w-5 h-5 text-accent-blue" />,
  draws: <Sparkles className="w-5 h-5 text-accent-neon" />,
  canceled: <XCircle className="w-5 h-5 text-status-canceled" />,
  other: <Bell className="w-5 h-5 text-text-secondary" />,
};

export const AlertsPage: React.FC = () => {
  const [items, setItems] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [pushGranted, setPushGranted] = useState<boolean | null>(null);
  const [respondingInvite, setRespondingInvite] = useState<number | null>(null);
  const push = usePushNotifications();

  useEffect(() => {
    if (push.isSupported) {
      setPushGranted(Notification.permission === 'granted');
    }
  }, [push.isSupported]);

  async function load() {
    setLoading(true);
    try {
      const data = await listAlerts();
      setItems(data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const dispatchUnread = (updatedItems: Alert[]) => {
    const count = updatedItems.filter((a) => a.status !== 'read').length;
    window.dispatchEvent(new CustomEvent('alerts-unread-changed', { detail: count }));
  };

  async function markRead(id: number) {
    try {
      await markAlertRead(id);
      setItems((prev) => {
        const next = prev.map((a) => (a.id === id ? { ...a, status: 'read' as const, read_at: new Date().toISOString() } : a));
        dispatchUnread(next);
        return next;
      });
    } catch { /* ignore */ }
  }

  async function handlePushToggle() {
    if (pushGranted) {
      const ok = await push.unsubscribe();
      if (ok) { setPushGranted(false); toast.success('Notificações push desativadas.'); }
      else if (push.error) toast.error(push.error);
    } else {
      const ok = await push.subscribe();
      if (ok) { setPushGranted(true); toast.success('Notificações push ativadas!'); }
      else if (push.error) toast.error(push.error);
    }
  }

  async function handleInviteResponse(alert: Alert, action: 'accept' | 'decline') {
    const inviteId = alert.payload?.invite_id as number | undefined;
    if (!inviteId) return;
    setRespondingInvite(alert.id);
    try {
      await respondDependentInvite(inviteId, action);
      if (action === 'accept') {
        toast.success('Convite aceito! Você agora é dependente do responsável.');
      } else {
        toast('Convite recusado.');
      }
      setItems((prev) => {
        const next = prev.filter((a) => a.id !== alert.id);
        dispatchUnread(next);
        return next;
      });
    } catch (err: any) {
      const httpStatus = err?.response?.status;
      // Invite already responded or canceled — remove the stale alert from the list
      if (httpStatus === 400) {
        setItems((prev) => {
          const next = prev.filter((a) => a.id !== alert.id);
          dispatchUnread(next);
          return next;
        });
        toast('Este convite já não está mais disponível.');
      } else {
        toast.error(extractApiError(err));
      }
    } finally {
      setRespondingInvite(null);
    }
  }

  async function markAll() {
    try {
      await markAllAlertsRead();
      toast.success('Alertas marcados como lidos');
      window.dispatchEvent(new CustomEvent('alerts-unread-changed', { detail: 0 }));
      load();
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  const unreadCount = items.filter((a) => a.status !== 'read').length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Alertas</h1>
          <p className="text-sm text-text-muted">
            {unreadCount > 0 ? `${unreadCount} não lidos` : 'Tudo em dia'}
          </p>
        </div>
        {unreadCount > 0 && (
          <button className="btn-ghost flex items-center gap-1 text-xs" onClick={markAll}>
            <CheckCheck className="w-4 h-4" /> Marcar todos
          </button>
        )}
      </div>

      {/* Push notification toggle */}
      {push.isSupported && (
        <div className="card flex items-center justify-between gap-3 !py-3">
          <div className="flex items-center gap-2">
            {pushGranted ? (
              <BellRing className="w-4 h-4 text-accent-neon" />
            ) : (
              <BellOff className="w-4 h-4 text-text-muted" />
            )}
            <div>
              <p className="text-sm font-medium text-text-primary">Notificações push</p>
              <p className="text-xs text-text-muted">
                {pushGranted ? 'Ativas — você receberá alertas mesmo com o app fechado' : 'Desativadas'}
              </p>
            </div>
          </div>
          <button
            onClick={handlePushToggle}
            disabled={push.loading}
            className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors ${
              pushGranted
                ? 'border-red-400/40 text-red-400 hover:bg-red-400/10'
                : 'border-accent-neon/40 text-accent-neon hover:bg-accent-neon/10'
            }`}
          >
            {push.loading ? <Loader2 className="w-3 h-3 animate-spin" /> : pushGranted ? 'Desativar' : 'Ativar'}
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card text-center py-10">
          <Bell className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="text-sm text-text-secondary">Nenhum alerta ainda.</p>
          <p className="text-xs text-text-muted mt-1">
            Adicione torneios à agenda para receber avisos.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((a) => {
            const isInvite = a.payload?.action === 'dependent_invite';
            const isRespondingThis = respondingInvite === a.id;
            // Show only the first sentence of the body to keep it clean
            const shortBody = a.body
              ? a.body.split(/[\n.!?]/)[0].trim()
              : null;
            return (
              <div
                key={a.id}
                onClick={() => !isInvite && a.status !== 'read' ? markRead(a.id) : undefined}
                className={`card !py-3 flex items-start gap-3 transition-colors ${
                  isInvite ? 'border-blue-500/30 bg-blue-500/5' : 'cursor-pointer hover:border-accent-neon/30'
                } ${a.status === 'read' && !isInvite ? 'opacity-50' : ''}`}
              >
                {/* Icon */}
                <div className="shrink-0 mt-0.5">
                  {isInvite ? <Users className="w-4 h-4 text-blue-400" /> : KIND_ICONS[a.kind]}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold leading-snug truncate">{a.title}</p>
                    <div className="flex items-center gap-2 shrink-0">
                      {a.status !== 'read' && (
                        <span className="w-1.5 h-1.5 rounded-full bg-accent-neon" />
                      )}
                      <span className="text-[10px] text-text-muted whitespace-nowrap">
                        {fmtRelative(a.created_at)}
                      </span>
                    </div>
                  </div>

                  {shortBody && (
                    <p className="text-xs text-text-muted mt-0.5 truncate">{shortBody}</p>
                  )}

                  {/* Actions row */}
                  {((!isInvite && a.edition) || isInvite) && (
                    <div className="flex items-center gap-2 mt-2">
                      {!isInvite && a.edition && (
                        <Link
                          to={`/torneios/${a.edition}`}
                          onClick={(e) => e.stopPropagation()}
                          className="flex items-center gap-1 text-[10px] text-accent-blue hover:underline"
                        >
                          <ExternalLink className="w-3 h-3" /> Ver torneio
                        </Link>
                      )}
                      {isInvite && (
                        <div className="flex gap-2 w-full">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleInviteResponse(a, 'decline'); }}
                            disabled={isRespondingThis}
                            className="flex-1 py-1.5 rounded-lg border border-red-400/40 text-red-400 text-xs font-bold hover:bg-red-400/10 disabled:opacity-50 transition-colors"
                          >
                            {isRespondingThis ? <Loader2 className="w-3 h-3 animate-spin mx-auto" /> : 'Recusar'}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleInviteResponse(a, 'accept'); }}
                            disabled={isRespondingThis}
                            className="flex-1 py-1.5 rounded-lg bg-blue-500 text-white text-xs font-bold hover:bg-blue-600 disabled:opacity-50 transition-colors"
                          >
                            {isRespondingThis ? <Loader2 className="w-3 h-3 animate-spin mx-auto" /> : 'Aceitar'}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
