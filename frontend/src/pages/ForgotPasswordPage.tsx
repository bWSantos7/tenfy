import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../services/api';

export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post('/api/auth/password-reset/', { email: email.trim().toLowerCase() });
    } catch {
      // Always show success to prevent user enumeration
    } finally {
      setSent(true);
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
          <h1 className="text-2xl font-bold">Recuperar senha</h1>
          <p className="text-text-muted text-sm mt-1">
            {sent ? 'Verifique seu e-mail' : 'Informe seu e-mail de cadastro'}
          </p>
        </div>

        {sent ? (
          <div className="card text-center space-y-4">
            <CheckCircle className="w-12 h-12 text-accent-neon mx-auto" />
            <p className="text-text-secondary text-sm">
              Se <span className="text-text-primary font-medium">{email}</span> estiver
              cadastrado, você receberá as instruções em instantes.
            </p>
            <p className="text-text-muted text-xs">
              Não recebeu? Verifique a caixa de spam ou tente novamente em alguns minutos.
            </p>
            <Link
              to="/login"
              className="btn-primary w-full flex items-center justify-center gap-2 text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              Voltar ao login
            </Link>
          </div>
        ) : (
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
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Enviar instruções
            </button>
            <Link
              to="/login"
              className="flex items-center justify-center gap-1 text-xs text-text-muted hover:text-accent-neon transition-colors"
            >
              <ArrowLeft className="w-3 h-3" />
              Voltar ao login
            </Link>
          </form>
        )}
      </div>
    </div>
  );
};
