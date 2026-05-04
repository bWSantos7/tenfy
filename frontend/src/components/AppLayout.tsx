import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, Calendar, Star, Bell, User, LogOut, ShieldCheck, Sun, Moon, Users, Award, CreditCard } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';

const navItems = [
  { to: '/', label: 'Início', icon: Home, end: true },
  { to: '/torneios', label: 'Torneios', icon: Calendar, end: false },
  { to: '/watchlist', label: 'Agenda', icon: Star, end: false },
  { to: '/resultados', label: 'Resultados', icon: Award, end: false },
  { to: '/alertas', label: 'Alertas', icon: Bell, end: false },
  { to: '/perfil', label: 'Perfil', icon: User, end: false },
];

export const AppLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { theme, toggle: toggleTheme } = useTheme();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-bg-base flex flex-col">
      <header className="sticky top-0 z-30 bg-bg-base/80 backdrop-blur-lg border-b border-border-subtle">
        <div className="mx-auto max-w-5xl px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent-neon flex items-center justify-center shadow-glow overflow-hidden">
              <img src="/icons/logo.png" alt="Tennis Hub" className="w-6 h-6 object-contain" style={{ filter: 'brightness(0)' }} />
            </div>
            <div>
              <div className="text-sm font-bold leading-tight">Tennis Hub</div>
              <div className="text-[10px] text-text-muted leading-tight">Tênis • Brasil</div>
            </div>
          </NavLink>
          <div className="flex items-center gap-1">
            {user?.role === 'coach' && (
              <NavLink
                to="/treinador"
                className="btn-ghost flex items-center gap-1 text-xs"
                title="Meus alunos"
              >
                <Users className="w-4 h-4" />
                <span className="hidden sm:inline">Alunos</span>
              </NavLink>
            )}
            <NavLink
              to="/assinatura"
              className="btn-ghost flex items-center gap-1 text-xs"
              title="Minha assinatura"
            >
              <CreditCard className="w-4 h-4" />
              <span className="hidden sm:inline">Assinatura</span>
            </NavLink>
            {user?.is_staff && (
              <NavLink
                to="/admin-panel"
                className="btn-ghost flex items-center gap-1 text-xs"
                title="Painel admin"
              >
                <ShieldCheck className="w-4 h-4" />
                <span className="hidden sm:inline">Admin</span>
              </NavLink>
            )}
            <button
              onClick={toggleTheme}
              className="btn-ghost !px-2"
              title={theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={handleLogout}
              className="btn-ghost flex items-center gap-1 text-xs"
              title="Sair"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Sair</span>
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-5xl px-4 pt-4 pb-24">
        <Outlet />
      </main>

      <nav className="fixed bottom-0 inset-x-0 z-30 bg-bg-card/95 backdrop-blur-lg border-t border-border-subtle">
        <div className="mx-auto max-w-5xl px-2 h-16 grid grid-cols-6">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-0.5 text-[10px] transition-colors ${
                  isActive
                    ? 'text-accent-neon'
                    : 'text-text-muted hover:text-text-primary'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={`w-5 h-5 ${isActive ? 'drop-shadow-[0_0_4px_#00FF88]' : ''}`} />
                  <span className="font-medium">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
};
