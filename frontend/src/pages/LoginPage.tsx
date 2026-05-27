import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { login } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';

export const LoginPage: React.FC = () => {
  const nav = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Se o usuário chegou ao login diretamente (sem ser redirecionado de uma rota protegida),
  // ou se veio da landing page ('/'), mandamos para /inicio após o login.
  const rawFrom = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
  const from = !rawFrom || rawFrom === '/' ? '/inicio' : rawFrom;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoginError(null);
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      setUser(data.user);
      toast.success('Bem-vindo de volta!');
      nav(from, { replace: true });
    } catch {
      setLoginError('E-mail ou senha incorretos. Verifique os dados ou redefina sua senha.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo largo — igual ao mobile */}
        <div className="flex justify-center mb-8">
          <img
            src="/icons/logo_login.png?v=3"
            alt="Tenfy Logo"
            className="h-12 object-contain"
            style={{ maxWidth: 200 }}
          />
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
          {loginError && (
            <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2.5">
              <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
              <span className="text-sm text-red-400">{loginError}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Entrar
          </button>
          <div className="text-center">
            <Link to="/recuperar-senha" className="text-xs text-text-muted hover:text-accent-neon transition-colors">
              Esqueceu a senha?
            </Link>
          </div>
        </form>

        <div className="text-center mt-4 text-sm text-text-secondary">
          Novo por aqui?{' '}
          <Link to="/register" className="text-accent-neon font-medium hover:underline">Criar conta</Link>
        </div>
      </div>
    </div>
  );
};
