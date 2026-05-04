import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../services/api';

export const ResetPasswordPage: React.FC = () => {
  const { uid, token } = useParams<{ uid: string; token: string }>();
  const nav = useNavigate();
  const [form, setForm] = useState({ new_password: '', confirm_password: '' });
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function update(k: keyof typeof form, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.new_password.length < 8) {
      toast.error('A senha precisa ter ao menos 8 caracteres');
      return;
    }
    if (form.new_password !== form.confirm_password) {
      toast.error('As senhas não conferem');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/api/auth/password-reset/confirm/', {
        uid,
        token,
        new_password: form.new_password,
        confirm_password: form.confirm_password,
      });
      toast.success('Senha redefinida! Faça login.');
      nav('/login', { replace: true });
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
          <h1 className="text-2xl font-bold">Nova senha</h1>
          <p className="text-text-muted text-sm mt-1">Crie uma senha segura</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4">
          <div>
            <label className="text-xs text-text-secondary font-medium mb-1 block">Nova senha</label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                required
                minLength={8}
                autoComplete="new-password"
                className="input-base pr-11"
                placeholder="Mínimo 8 caracteres"
                value={form.new_password}
                onChange={(e) => update('new_password', e.target.value)}
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
          <div>
            <label className="text-xs text-text-secondary font-medium mb-1 block">
              Confirme a nova senha
            </label>
            <input
              type={showPwd ? 'text' : 'password'}
              required
              minLength={8}
              autoComplete="new-password"
              className="input-base"
              placeholder="Repita a senha"
              value={form.confirm_password}
              onChange={(e) => update('confirm_password', e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Redefinir senha
          </button>
        </form>

        <div className="text-center mt-4 text-sm text-text-secondary">
          <Link to="/login" className="text-accent-neon font-medium hover:underline">
            Voltar ao login
          </Link>
        </div>
      </div>
    </div>
  );
};
