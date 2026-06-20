import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Home, Calendar, Star, User, ShieldCheck, Sun, Moon, Award, Users, Bell, LogOut, UserCheck, Loader2, CreditCard, HelpCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { BetaModal } from './BetaModal';
import { InteractiveTutorial } from './InteractiveTutorial';
import { unreadAlerts, listReceivedInvites, respondDependentInvite } from '../services/data';
import { fetchSubscription } from '../services/billing';
import { DependentInvite } from '../types';

// Rotas liberadas mesmo com assinatura paga pendente (para o usuário conseguir pagar/gerenciar).
const ALLOWED_WHEN_UNPAID = ['/assinatura', '/configuracoes'];

// Nav principal — aparece no bottom bar (mobile) e no header (desktop)
const navItems = [
  { to: '/inicio',    label: 'Início',    icon: Home,     end: true  },
  { to: '/torneios',  label: 'Torneios',  icon: Calendar, end: false },
  { to: '/watchlist', label: 'Agenda',    icon: Star,     end: false },
  { to: '/resultados',label: 'Resultados',icon: Award,    end: false },
  { to: '/perfil',    label: 'Perfil',    icon: User,     end: false },
];

export const AppLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { theme, toggle: toggleTheme } = useTheme();
  const [unreadCount, setUnreadCount] = useState(0);
  const [pendingInvites, setPendingInvites] = useState<DependentInvite[]>([]);
  const [respondingInvite, setRespondingInvite] = useState<number | null>(null);
  // Paywall — bloqueia o app quando há plano pago pendente/inadimplente até confirmar o pagamento.
  const [paywall, setPaywall] = useState<{ checked: boolean; blocked: boolean }>({ checked: false, blocked: false });

  useEffect(() => {
    let active = true;
    fetchSubscription()
      .then((s) => {
        const paid = s.plan_slug === 'individual' || s.plan_slug === 'familia';
        const unpaid = s.status === 'pending' || s.status === 'unpaid';
        if (active) setPaywall({ checked: true, blocked: paid && unpaid });
      })
      .catch(() => { if (active) setPaywall({ checked: true, blocked: false }); });
    return () => { active = false; };
  }, [user?.id, location.pathname]);

  const paywallBlocking = paywall.blocked && !ALLOWED_WHEN_UNPAID.includes(location.pathname);

  const refreshUnread = () =>
    unreadAlerts().then((a) => setUnreadCount(Array.isArray(a) ? a.length : 0)).catch(() => {});

  // Refresh on every route change (catches returning from /alertas after marking as read)
  useEffect(() => { refreshUnread(); }, [location.pathname]);

  // Also listen for immediate updates dispatched by AlertsPage
  useEffect(() => {
    const handler = (e: Event) => setUnreadCount((e as CustomEvent<number>).detail);
    window.addEventListener('alerts-unread-changed', handler);
    return () => window.removeEventListener('alerts-unread-changed', handler);
  }, []);

  // Check pending invites on login (for non-parent users who may have received an invite)
  useEffect(() => {
    if (!user || user.role === 'parent') return;
    listReceivedInvites()
      .then((invites) => setPendingInvites(invites.filter((i) => i.status === 'pending' && !i.is_expired)))
      .catch(() => {});
  }, [user?.id]);

  async function handleInviteResponse(invite: DependentInvite, action: 'accept' | 'decline') {
    setRespondingInvite(invite.id);
    try {
      await respondDependentInvite(invite.id, action);
      setPendingInvites((prev) => prev.filter((i) => i.id !== invite.id));
      toast.success(action === 'accept' ? 'Vínculo aceito! Você agora é dependente do responsável.' : 'Convite recusado.');
    } catch {
      toast.error('Não foi possível processar o convite. Tente novamente.');
    } finally {
      setRespondingInvite(null);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col">
      <BetaModal user={user} />
      <InteractiveTutorial user={user} />

      {/* ── Modal de convite de vínculo pendente ──────────────────────────── */}
      {pendingInvites.length > 0 && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
          <div className="bg-bg-card border border-accent-blue/30 rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-accent-blue/15 flex items-center justify-center shrink-0">
                <Users className="w-5 h-5 text-accent-blue" />
              </div>
              <div>
                <h2 className="font-bold text-base">Solicitação de vínculo</h2>
                <p className="text-xs text-text-muted mt-0.5">
                  <span className="font-semibold text-text-primary">
                    {pendingInvites[0].parent_detail.full_name}
                  </span>{' '}
                  quer te vincular como dependente na plataforma Tenfy.
                </p>
              </div>
            </div>
            <p className="text-xs text-text-secondary">
              Ao aceitar, o responsável poderá visualizar e gerenciar seu perfil esportivo.
              Você pode recusar a qualquer momento.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => handleInviteResponse(pendingInvites[0], 'decline')}
                disabled={respondingInvite === pendingInvites[0].id}
                className="flex-1 py-2 rounded-xl border border-red-400/40 text-red-400 text-sm font-bold hover:bg-red-400/10 disabled:opacity-50 transition-colors"
              >
                {respondingInvite === pendingInvites[0].id ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Recusar'}
              </button>
              <button
                onClick={() => handleInviteResponse(pendingInvites[0], 'accept')}
                disabled={respondingInvite === pendingInvites[0].id}
                className="flex-1 py-2 rounded-xl bg-accent-blue text-white text-sm font-bold hover:opacity-90 disabled:opacity-50 transition-colors"
              >
                {respondingInvite === pendingInvites[0].id ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Aceitar'}
              </button>
            </div>
            {pendingInvites.length > 1 && (
              <p className="text-[11px] text-text-muted text-center">
                +{pendingInvites.length - 1} outro{pendingInvites.length > 2 ? 's' : ''} convite{pendingInvites.length > 2 ? 's' : ''} pendente{pendingInvites.length > 2 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ─── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 bg-bg-card/90 backdrop-blur-lg border-b border-border-subtle shadow-sm">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center gap-2">

          {/* Logo — clara (light) e escura (dark) */}
          <NavLink to="/inicio" className="flex items-center shrink-0 mr-3">
            <img src="/logos/logo_clara.png" alt="Tenfy" className="h-9 w-auto object-contain dark:hidden" />
            <img src="/logos/logo_escura.png" alt="Tenfy" className="h-9 w-auto object-contain hidden dark:block" />
          </NavLink>

          {/* ── Nav items — só visível em desktop (md+) ── */}
          <nav className="hidden md:flex items-center gap-0.5 flex-1">
            {navItems.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-semibold transition-colors ${
                    isActive
                      ? 'bg-accent-neon/10 text-accent-neon'
                      : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Spacer para mobile (empurra utilitários para a direita) */}
          <div className="flex-1 md:hidden" />

          {/* ── Utilitários ── */}
          <div className="flex items-center gap-0.5 shrink-0">
            {user?.role === 'coach' && (
              <NavLink to="/treinador" className="btn-ghost flex items-center gap-1 text-xs" title="Meus alunos">
                <Users className="w-4 h-4" />
                <span className="hidden lg:inline">Alunos</span>
              </NavLink>
            )}

            {/* Sino de alertas */}
            <NavLink to="/alertas" className="btn-ghost relative !px-2" title="Alertas">
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-accent-neon rounded-full flex items-center justify-center text-[10px] font-bold px-1"
                  style={{ color: 'rgb(var(--btn-text))' }}>
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </NavLink>

            {user?.is_staff && (
              <NavLink to="/admin-panel" className="btn-ghost flex items-center gap-1 text-xs" title="Painel admin">
                <ShieldCheck className="w-4 h-4" />
                <span className="hidden lg:inline">Admin</span>
              </NavLink>
            )}

            <button onClick={toggleTheme} className="btn-ghost !px-2" title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}>
              {theme === 'dark' ? <Sun className="w-4 h-4 text-accent-neon" /> : <Moon className="w-4 h-4" />}
            </button>

            <NavLink to="/ajuda" className="btn-ghost !px-2" title="Ajuda">
              <HelpCircle className="w-5 h-5" />
            </NavLink>

            <button
              onClick={() => logout()}
              className="btn-ghost !px-2 text-red-400 hover:text-red-500"
              title="Sair da conta"
            >
              <LogOut className="w-4 h-4" />
            </button>

          </div>
        </div>
      </header>

      {/* ─── Content ──────────────────────────────────────────────────────────── */}
      {/* pb-24 no mobile (espaço para bottom nav); pb-6 no desktop */}
      <main className="flex-1 mx-auto w-full max-w-6xl px-4 pt-4 pb-24 md:pb-8">
        {paywallBlocking ? (
          <div className="max-w-md mx-auto card text-center py-10 space-y-4 mt-6">
            <CreditCard className="w-10 h-10 text-accent-neon mx-auto" />
            <div>
              <p className="font-semibold text-lg">Pagamento pendente</p>
              <p className="text-sm text-text-muted mt-1">
                Sua assinatura ainda não foi confirmada. Conclua o pagamento para liberar o acesso ao Tenfy.
              </p>
            </div>
            <NavLink to="/assinatura" className="btn-primary inline-flex items-center gap-2">
              <CreditCard className="w-4 h-4" /> Concluir pagamento
            </NavLink>
            <button onClick={logout} className="block w-full text-xs text-text-muted hover:text-text-secondary mt-2">
              Sair
            </button>
          </div>
        ) : (
          <Outlet />
        )}
      </main>

      {/* ─── Bottom nav — apenas mobile (< md) ───────────────────────────────── */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-bg-card/95 backdrop-blur-lg border-t border-border-subtle">
        <div className="mx-auto max-w-6xl px-1 h-16 grid grid-cols-5">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-0.5 text-[9px] font-semibold transition-colors ${
                  isActive ? 'text-accent-neon' : 'text-text-muted hover:text-text-secondary'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`p-1.5 rounded-xl transition-colors ${isActive ? 'bg-accent-neon/10' : ''}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className="truncate max-w-[52px] text-center">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
};
