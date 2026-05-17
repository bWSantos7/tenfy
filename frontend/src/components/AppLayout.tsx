import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, Calendar, Star, User, LogOut, ShieldCheck, Sun, Moon, Award, CreditCard, Users, Bell } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { BetaModal } from './BetaModal';
import { unreadAlerts } from '../services/data';

// Mobile: Alertas fica fora do nav inferior — acesso pelo sino no header
const navItems = [
  { to: '/', label: 'Início',      icon: Home,     end: true  },
  { to: '/torneios', label: 'Torneios',   icon: Calendar, end: false },
  { to: '/watchlist', label: 'Agenda',     icon: Star,     end: false },
  { to: '/resultados', label: 'Resultados', icon: Award,    end: false },
  { to: '/perfil',    label: 'Perfil',     icon: User,     end: false },
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

      {/* ─── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 bg-bg-card/90 backdrop-blur-lg border-b border-border-subtle shadow-sm">
        <div className="mx-auto max-w-5xl px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2.5">
            <img src="/logo2.png" alt="Tenfy" className="h-7 object-contain" style={{ maxWidth: 120 }} />
          </NavLink>

          <div className="flex items-center gap-1">
            {user?.role === 'coach' && (
              <NavLink to="/treinador" className="btn-ghost flex items-center gap-1 text-xs" title="Meus alunos">
                <Users className="w-4 h-4" />
                <span className="hidden sm:inline">Alunos</span>
              </NavLink>
            )}

            {/* Sino de alertas — igual ao mobile (badge com contagem) */}
            <NavLink to="/alertas" className="btn-ghost relative !px-2" title="Alertas">
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-accent-neon rounded-full flex items-center justify-center text-[10px] font-bold px-1"
                  style={{ color: 'rgb(var(--btn-text))' }}>
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </NavLink>

            <NavLink to="/assinatura" className="btn-ghost flex items-center gap-1 text-xs" title="Minha assinatura">
              <CreditCard className="w-4 h-4" />
              <span className="hidden sm:inline">Assinatura</span>
            </NavLink>

            {user?.is_staff && (
              <NavLink to="/admin-panel" className="btn-ghost flex items-center gap-1 text-xs" title="Painel admin">
                <ShieldCheck className="w-4 h-4" />
                <span className="hidden sm:inline">Admin</span>
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

      {/* ─── Content ─────────────────────────────────────────────────────── */}
      <main className="flex-1 mx-auto w-full max-w-5xl px-4 pt-4 pb-24">
        <Outlet />
      </main>

      {/* ─── Bottom nav (5 tabs, igual ao mobile) ────────────────────────── */}
      <nav className="fixed bottom-0 inset-x-0 z-30 bg-bg-card/95 backdrop-blur-lg border-t border-border-subtle">
        <div className="mx-auto max-w-5xl px-2 h-16 grid grid-cols-5">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors ${
                  isActive ? 'text-accent-neon' : 'text-text-muted hover:text-text-secondary'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`p-1.5 rounded-xl transition-colors ${isActive ? 'bg-accent-neon/10' : ''}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
};
