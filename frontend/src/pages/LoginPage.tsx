import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { login } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';
import { extractApiError } from '../services/api';

export const LoginPage: React.FC = () => {
  const nav = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/';

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      setUser(data.user);
      toast.success('Bem-vindo de volta!');
      nav(from, { replace: true });
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-accent-neon flex items-center justify-center shadow-glow mb-4 overflow-hidden">
            <img src="/icons/logo.png" alt="Tennis Hub" className="w-12 h-12 object-contain" style={{ filter: 'brightness(0)' }} />
          </div>
          <h1 className="text-2xl font-bold">Tennis Hub</h1>
          <p className="text-text-muted text-sm mt-1">Seu hub de torneios de tênis</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4">
          <div>
            <label className="text-xs text-text-secondary font-medium mb-1 block">E-mail</label>
            <input
              type="email"
              required
              autoComplete="email"
              className="input-base"
              placeholder="voce@exemplo.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-text-secondary font-medium mb-1 block">Senha</label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                required
                autoComplete="current-password"
                className="input-base pr-11"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                className="absolute inset-y-0 right-3 flex items-center text-text-muted hover:text-text-primary"
              >
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Entrar
          </button>

          <div className="text-center">
            <Link
              to="/recuperar-senha"
              className="text-xs text-text-muted hover:text-accent-neon transition-colors"
            >
              Esqueceu a senha?
            </Link>
          </div>
        </form>

        <div className="text-center mt-4 text-sm text-text-secondary">
          Novo por aqui?{' '}
          <Link to="/register" className="text-accent-neon font-medium hover:underline">
            Criar conta
          </Link>
        </div>
      </div>
    </div>
  );
};
