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
    <div className="min-h-screen bg-bg-base relative overflow-hidden flex flex-col items-center justify-center px-4 py-8">

      {/* Decorative background glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-48 -right-48 w-[600px] h-[600px] bg-accent-neon/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-48 -left-48 w-[600px] h-[600px] bg-accent-blue/5 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">

        {/* Logo */}
        <div className="flex justify-center mb-8">
          <img
            src="/logos/logo1.png"
            alt="Tenfy"
            className="h-16 object-contain dark:hidden"
            style={{ maxWidth: 270 }}
          />
          <img
            src="/logos/logo6.png"
            alt="Tenfy"
            className="h-14 object-contain hidden dark:block"
            style={{ maxWidth: 250 }}
          />
        </div>

        {/* Card */}
        <div className="bg-bg-card border border-border-subtle rounded-2xl p-6 shadow-card">

          <div className="mb-5">
            <h1 className="text-xl font-bold text-text-primary">Bem-vindo de volta</h1>
            <p className="text-sm text-text-muted mt-1">Entre com sua conta Tenfy</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-text-secondary font-medium mb-1.5 block">E-mail</label>
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
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs text-text-secondary font-medium">Senha</label>
                <Link
                  to="/recuperar-senha"
                  className="text-xs text-text-muted hover:text-accent-neon transition-colors"
                >
                  Esqueceu?
                </Link>
              </div>
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
              className="btn-primary w-full flex items-center justify-center gap-2 mt-1"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Entrar
            </button>
          </form>
        </div>

        <div className="text-center mt-5 text-sm text-text-secondary">
          Não tem conta?{' '}
          <Link to="/register" className="text-accent-neon font-semibold hover:underline">
            Criar conta grátis
          </Link>
        </div>

      </div>
    </div>
  );
};
