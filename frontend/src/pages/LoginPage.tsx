import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2, AlertCircle, Calendar, ShieldCheck, Bell, ArrowRight } from 'lucide-react';
import toast from 'react-hot-toast';
import { login } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';

const features = [
  { icon: Calendar,     text: 'Calendário unificado de torneios' },
  { icon: ShieldCheck,  text: 'Análise de elegibilidade por categoria' },
  { icon: Bell,         text: 'Alertas de prazo de inscrição' },
];

export const LoginPage: React.FC = () => {
  const nav = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd]   = useState(false);
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
    <div className="min-h-screen flex">

      {/* ─── PAINEL ESQUERDO — visível apenas em lg+ ─────────────────────────── */}
      <div className="hidden lg:flex lg:w-[52%] xl:w-[55%] relative overflow-hidden flex-col"
        style={{ background: 'linear-gradient(145deg, #0A1330 0%, #0f1e4a 60%, #0A1330 100%)' }}>

        {/* Grade decorativa sutil */}
        <div className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: 'linear-gradient(rgba(198,239,33,1) 1px, transparent 1px), linear-gradient(90deg, rgba(198,239,33,1) 1px, transparent 1px)',
            backgroundSize: '48px 48px',
          }} />

        {/* Brilhos de fundo */}
        <div className="absolute -top-40 -left-40 w-[480px] h-[480px] bg-accent-neon/8 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[360px] h-[360px] bg-accent-blue/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-accent-neon/3 rounded-full blur-3xl pointer-events-none" />

        {/* Círculos decorativos (bola de tênis estilizada) */}
        <div className="absolute bottom-24 right-10 w-72 h-72 rounded-full border border-accent-neon/8" />
        <div className="absolute bottom-16 right-2  w-56 h-56 rounded-full border border-accent-neon/5" />

        <div className="relative flex flex-col h-full p-10 xl:p-14">

          {/* Logo principal — centralizada na área livre à direita do texto */}
          <img
            src="/logos/logo_escura2.png"
            alt="Tenfy"
            className="absolute top-[46%] left-[68%] -translate-x-1/2 -translate-y-1/2 w-[42%] max-w-[400px] max-h-[36vh] object-contain drop-shadow-2xl pointer-events-none select-none"
          />

          {/* Texto no topo */}
          <div className="relative pt-4">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-7 border"
              style={{ background: 'rgba(198,239,33,0.08)', borderColor: 'rgba(198,239,33,0.2)' }}>
              <span className="w-2 h-2 rounded-full bg-accent-neon animate-pulse" />
              <span className="text-accent-neon text-xs font-semibold tracking-wider uppercase">Plataforma ao vivo</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl xl:text-[2.75rem] font-extrabold text-white leading-[1.15] mb-5">
              Seu calendário<br />
              <span className="text-accent-neon">inteligente</span><br />
              de torneios
            </h1>

            <p className="text-white/55 text-[15px] leading-relaxed mb-10 max-w-xs">
              Centralize torneios de todas as federações e nunca mais perca um prazo de inscrição.
            </p>

            {/* Features */}
            <div className="space-y-3.5">
              {features.map(({ icon: Icon, text }) => (
                <div key={text} className="flex items-center gap-3.5">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: 'rgba(198,239,33,0.1)', border: '1px solid rgba(198,239,33,0.2)' }}>
                    <Icon className="w-4 h-4 text-accent-neon" />
                  </div>
                  <span className="text-white/75 text-sm font-medium">{text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Card flutuante inferior */}
          <div className="relative mt-auto">
            <div className="rounded-2xl p-4 backdrop-blur-sm"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: 'rgba(198,239,33,0.12)' }}>
                  <Calendar className="w-5 h-5 text-accent-neon" />
                </div>
                <div className="min-w-0">
                  <p className="text-white text-sm font-semibold leading-tight">Torneios disponíveis</p>
                  <p className="text-white/40 text-xs mt-0.5">Calendário sempre atualizado</p>
                </div>
                <ArrowRight className="w-4 h-4 text-white/25 ml-auto shrink-0" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── PAINEL DIREITO — formulário ─────────────────────────────────────── */}
      <div className="flex-1 bg-bg-base dark:bg-bg-elevated flex flex-col items-center justify-center px-6 py-12 relative overflow-hidden">

        {/* Brilhos de fundo (mobile) */}
        <div className="lg:hidden absolute inset-0 pointer-events-none">
          <div className="absolute -top-32 -right-32 w-96 h-96 bg-accent-neon/5 rounded-full blur-3xl" />
          <div className="absolute -bottom-32 -left-32 w-96 h-96 bg-accent-blue/5 rounded-full blur-3xl" />
        </div>

        <div className="relative w-full max-w-md">

          {/* Logo — apenas mobile/tablet */}
          <div className="flex justify-center mb-10 lg:hidden">
            <img src="/logos/logo_clara.png" alt="Tenfy" className="h-20 w-auto object-contain dark:hidden" />
            <img src="/logos/logo_escura.png" alt="Tenfy" className="h-20 w-auto object-contain hidden dark:block" />
          </div>

          {/* Cabeçalho do formulário */}
          <div className="mb-8">
            <h2 className="text-3xl font-extrabold text-text-primary tracking-tight">Bem-vindo de volta</h2>
            <p className="text-text-muted text-sm mt-1.5">Entre com sua conta Tenfy para continuar</p>
          </div>

          {/* Card do formulário */}
          <div className="bg-bg-card border border-border-subtle rounded-2xl p-6 shadow-card-dark">
            <form onSubmit={onSubmit} className="space-y-5">

              {/* E-mail */}
              <div>
                <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-widest mb-2">
                  E-mail
                </label>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  className="input-base"
                  placeholder="voce@exemplo.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email"
                />
              </div>

              {/* Senha */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[11px] font-bold text-text-secondary uppercase tracking-widest">
                    Senha
                  </label>
                  <Link
                    to="/recuperar-senha"
                    className="text-xs text-accent-neon font-semibold hover:underline"
                  >
                    Esqueceu a senha?
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
                    data-testid="login-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute inset-y-0 right-3 flex items-center text-text-muted hover:text-text-primary transition-colors"
                    tabIndex={-1}
                  >
                    {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Erro de login */}
              {loginError && (
                <div className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/20 rounded-xl px-3.5 py-3" data-testid="login-error">
                  <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <span className="text-sm text-red-400 leading-snug">{loginError}</span>
                </div>
              )}

              {/* Botão */}
              <button
                type="submit"
                disabled={submitting}
                className="btn-primary w-full flex items-center justify-center gap-2 !py-3.5 text-[15px] font-bold mt-1"
                data-testid="login-submit"
              >
                {submitting
                  ? <><Loader2 className="w-5 h-5 animate-spin" /> Entrando...</>
                  : <><ArrowRight className="w-5 h-5" /> Entrar na conta</>
                }
              </button>
            </form>
          </div>

          {/* Link cadastro */}
          <p className="text-center mt-6 text-sm text-text-secondary">
            Não tem conta?{' '}
            <Link to="/register" className="text-accent-neon font-bold hover:underline">
              Criar conta grátis
            </Link>
          </p>

          {/* Link privacidade */}
          <p className="text-center mt-3 text-[11px] text-text-muted">
            Ao entrar, você concorda com nossa{' '}
            <Link to="/privacidade" className="hover:text-text-secondary underline transition-colors">
              Política de Privacidade
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};
