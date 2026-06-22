import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock, Mail } from 'lucide-react';
import toast from 'react-hot-toast';
import { login, logout } from '../services/auth';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export const PartnerLoginPage: React.FC = () => {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const res = await login(email.trim(), password);
      if (res.user?.role !== 'partner') {
        // Não é uma conta de parceiro — não deixa entrar na área.
        await logout();
        setUser(null);
        toast.error('Esta conta não é de parceiro. Use o acesso de parceiro fornecido pela Tenfy.');
        return;
      }
      setUser(res.user);
      nav('/parceiro', { replace: true });
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-6">
          <img src="/logos/logo_clara.png" alt="Tenfy" className="h-20 w-auto object-contain dark:hidden" />
          <img src="/logos/logo_escura.png" alt="Tenfy" className="h-12 w-auto object-contain hidden dark:block" />
        </div>

        <div className="card !p-6 space-y-4">
          <div className="text-center">
            <h1 className="text-lg font-bold">Área do Parceiro</h1>
            <p className="text-xs text-text-muted mt-1">
              Acompanhe seus cupons e resultados.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-text-muted mb-1 block">E-mail</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  className="input-base w-full text-sm pl-9"
                  type="email"
                  autoComplete="email"
                  placeholder="voce@exemplo.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Senha</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  className="input-base w-full text-sm pl-9"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>
            <button className="btn-primary w-full !text-sm" type="submit" disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : null}
              Entrar
            </button>
          </form>

          <p className="text-[11px] text-text-muted text-center">
            O acesso de parceiro é criado pela equipe Tenfy. Em caso de dúvida, fale com seu contato.
          </p>
        </div>
      </div>
    </div>
  );
};
