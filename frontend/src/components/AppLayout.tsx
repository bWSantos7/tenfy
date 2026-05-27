import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, Calendar, Star, User, LogOut, ShieldCheck, Sun, Moon, Award, CreditCard, Users, Bell } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { BetaModal } from './BetaModal';
import { unreadAlerts } from '../services/data';

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
  const navigate = useNavigate();
  const { theme, toggle: toggleTheme } = useTheme();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    unreadAlerts().then((a) => setUnreadCount(Array.isArray(a) ? a.length : 0)).catch(() => {});
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-bg-base flex flex-col">
      <BetaModal user={user} />

      {/* ─── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 bg-bg-card/90 backdrop-blur-lg border-b border-border-subtle shadow-sm">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center gap-2">

          {/* Logo */}
          <NavLink to="/inicio" className="flex items-center gap-2 shrink-0 mr-2">
            <img src={theme === 'dark' ? '/icons/logo_noturno.png?v=2' : '/icons/logo_diurna.png?v=2'} alt="Tenfy" className="h-7 object-contain" style={{ maxWidth: 110 }} />
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

            <NavLink to="/assinatura" className="btn-ghost flex items-center gap-1 text-xs hidden sm:flex" title="Minha assinatura">
              <CreditCard className="w-4 h-4" />
              <span className="hidden lg:inline">Assinatura</span>
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

            <button onClick={handleLogout} className="btn-ghost flex items-center gap-1 text-xs" title="Sair">
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Sair</span>
            </button>
          </div>
        </div>
      </header>

      {/* ─── Content ──────────────────────────────────────────────────────────── */}
      {/* pb-24 no mobile (espaço para bottom nav); pb-6 no desktop */}
      <main className="flex-1 mx-auto w-full max-w-6xl px-4 pt-4 pb-24 md:pb-8">
        <Outlet />
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
