import React, { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle, Loader2, Mail } from 'lucide-react';
import toast from 'react-hot-toast';
import { register, sendEmailOtp, verifyEmailOtp } from '../services/auth';
import { createProfile } from '../services/data';
import { useAuth } from '../contexts/AuthContext';
import { extractApiError } from '../services/api';
import { User } from '../types';

type Step = 'form' | 'email_otp' | 'profile_info' | 'profile_location' | 'profile_level';

const STATES = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];
const LEVELS = [
  { value: 'beginner', label: 'Principiante' },
  { value: 'amateur', label: 'Amador' },
  { value: 'federated', label: 'Federado' },
  { value: 'youth', label: 'Juvenil' },
  { value: 'pro', label: 'Profissional' },
];
const CLASSES = ['1', '2', '3', '4', '5', 'PR'];

export const RegisterPage: React.FC = () => {
  const nav = useNavigate();
  const { setUser } = useAuth();

  const [step, setStep] = useState<Step>('form');
  const [registeredUser, setRegisteredUser] = useState<User | null>(null);
  const [duplicateEmail, setDuplicateEmail] = useState(false);
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    password: '',
    password_confirm: '',
    role: 'player',
    accept_terms: false,
    marketing_consent: false,
  });
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '' as 'M' | 'F' | '',
    home_state: 'SP',
    home_city: '',
    travel_radius_km: 100,
    competitive_level: 'amateur',
    tennis_class: '',
  });
  const [emailCode, setEmailCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const emailInputRef = useRef<HTMLInputElement>(null);

  function updateForm<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    if (k === 'email') setDuplicateEmail(false);
  }
  function updateProfile<K extends keyof typeof profile>(k: K, v: (typeof profile)[K]) {
    setProfile((p) => ({ ...p, [k]: v }));
  }

  const steps: Step[] = ['form', 'email_otp', 'profile_info', 'profile_location', 'profile_level'];
  const stepIdx = steps.indexOf(step);
  const stepLabels = ['Dados', 'E-mail', 'Perfil', 'Local', 'Nível'];

  // ─── Step 1: Register ────────────────────────────────────────────────────
  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    if (form.password !== form.password_confirm) { toast.error('As senhas não conferem'); return; }
    if (form.password.length < 8) { toast.error('A senha precisa ter ao menos 8 caracteres'); return; }
    setSubmitting(true);
    try {
      const data = await register({ ...form });
      setRegisteredUser(data.user);
      setProfile((p) => ({ ...p, display_name: form.full_name }));
      if (data.email_otp_sent === false) {
        toast('Conta criada, mas não conseguimos enviar o código agora. Tente reenviar em instantes.');
      } else {
        toast.success('Conta criada! Verifique seu e-mail.');
      }
      setStep('email_otp');
      setTimeout(() => emailInputRef.current?.focus(), 100);
    } catch (err) {
      const msg = extractApiError(err);
      if (msg.toLowerCase().includes('email') && msg.toLowerCase().includes('existe')) {
        setDuplicateEmail(true);
      } else {
        toast.error(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ─── Step 2: Verify email OTP ────────────────────────────────────────────
  async function onVerifyEmail(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await verifyEmailOtp(emailCode.trim());
      toast.success('E-mail verificado!');
      setStep('profile_info');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // ─── Step 5: Finish ──────────────────────────────────────────────────────
  async function onFinish() {
    setSubmitting(true);
    try {
      await createProfile({
        display_name: profile.display_name || form.full_name || 'Jogador',
        birth_year: profile.birth_year ? Number(profile.birth_year) : null,
        gender: profile.gender || undefined,
        home_state: profile.home_state,
        home_city: profile.home_city,
        travel_radius_km: profile.travel_radius_km,
        competitive_level: profile.competitive_level as any,
        tennis_class: profile.tennis_class,
        is_primary: true,
      } as any);
      toast.success('Perfil criado! Bem-vindo!');
      if (registeredUser) setUser(registeredUser);
      nav('/', { replace: true });
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function resendEmailOtp() {
    setResending(true);
    try {
      await sendEmailOtp();
      toast.success('Novo código enviado ao e-mail.');
    } catch {
      toast.error('Não foi possível reenviar. Tente em instantes.');
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">

        {/* Header */}
        <div className="flex flex-col items-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-accent-neon flex items-center justify-center shadow-glow mb-3 overflow-hidden">
            <img src="/icons/logo.png" alt="Tennis Hub" className="w-10 h-10 object-contain" style={{ filter: 'brightness(0)' }} />
          </div>
          <h1 className="text-xl font-bold">Criar conta</h1>
        </div>

        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {steps.map((s, i) => (
            <React.Fragment key={s}>
              <div className="flex flex-col items-center gap-1">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                  i < stepIdx ? 'bg-accent-neon text-bg-base'
                  : i === stepIdx ? 'bg-accent-neon text-bg-base ring-2 ring-accent-neon ring-offset-2 ring-offset-bg-base'
                  : 'bg-bg-card text-text-muted border border-border'
                }`}>
                  {i < stepIdx ? <CheckCircle className="w-3.5 h-3.5" /> : i + 1}
                </div>
                <span className="text-[10px] text-text-muted">{stepLabels[i]}</span>
              </div>
              {i < steps.length - 1 && (
                <div className={`h-px w-6 mb-4 transition-colors ${i < stepIdx ? 'bg-accent-neon' : 'bg-border'}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* ─── Step 1: Form ─────────────────────────────────────────────── */}
        {step === 'form' && (
          <form onSubmit={onRegister} className="card space-y-3">
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome completo</label>
              <input className="input-base" placeholder="Seu nome completo" value={form.full_name}
                onChange={(e) => updateForm('full_name', e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">E-mail *</label>
              <input type="email" required autoComplete="email"
                className={`input-base ${duplicateEmail ? 'border-red-500 focus:ring-red-500' : ''}`}
                placeholder="voce@exemplo.com" value={form.email}
                onChange={(e) => updateForm('email', e.target.value)} />
              {duplicateEmail && (
                <div className="mt-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400 space-y-1">
                  <p className="font-medium">Este e-mail já possui cadastro.</p>
                  <p>
                    <Link to="/login" className="underline text-accent-neon">Entrar</Link>{' '}ou{' '}
                    <Link to="/recuperar-senha" className="underline text-accent-neon">recuperar senha</Link>.
                  </p>
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Celular <span className="text-text-muted">(opcional, com DDD)</span></label>
              <input type="tel" autoComplete="tel" className="input-base" placeholder="11999999999"
                value={form.phone} onChange={(e) => updateForm('phone', e.target.value.replace(/\D/g, ''))} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Perfil</label>
              <select className="input-base" value={form.role} onChange={(e) => updateForm('role', e.target.value)}>
                <option value="player">Jogador</option>
                <option value="coach">Treinador</option>
                <option value="parent">Pai/Responsável</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Senha *</label>
              <input type="password" required minLength={8} autoComplete="new-password"
                className="input-base" placeholder="Mínimo 8 caracteres"
                value={form.password} onChange={(e) => updateForm('password', e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Confirme a senha *</label>
              <input type="password" required minLength={8} autoComplete="new-password"
                className="input-base" value={form.password_confirm}
                onChange={(e) => updateForm('password_confirm', e.target.value)} />
            </div>
            <label className="flex items-start gap-2 text-xs text-text-secondary cursor-pointer">
              <input type="checkbox" required className="mt-0.5 accent-accent-neon shrink-0"
                checked={form.accept_terms} onChange={(e) => updateForm('accept_terms', e.target.checked)} />
              <span>Li e aceito os termos de uso e a política de privacidade.</span>
            </label>
            <label className="flex items-start gap-2 text-xs text-text-secondary cursor-pointer">
              <input type="checkbox" className="mt-0.5 accent-accent-neon shrink-0"
                checked={form.marketing_consent} onChange={(e) => updateForm('marketing_consent', e.target.checked)} />
              <span>Quero receber e-mails com novidades e dicas.</span>
            </label>
            <p className="text-[11px] text-text-muted leading-relaxed">
              Ao criar sua conta, você concorda com o tratamento dos seus dados conforme a{' '}
              <a href="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"
                target="_blank" rel="noopener noreferrer" className="underline text-accent-neon">
                LGPD — Lei nº 13.709/2018
              </a>.
            </p>
            <button type="submit" disabled={submitting}
              className="btn-primary w-full flex items-center justify-center gap-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Criar conta
            </button>
          </form>
        )}

        {/* ─── Step 2: Email OTP ────────────────────────────────────────── */}
        {step === 'email_otp' && (
          <form onSubmit={onVerifyEmail} className="card space-y-4">
            <div className="flex flex-col items-center gap-2 text-center">
              <Mail className="w-10 h-10 text-accent-neon" />
              <p className="text-sm text-text-secondary">
                Enviamos um código de 6 dígitos para{' '}
                <span className="text-text-primary font-medium">{form.email}</span>
              </p>
              <p className="text-xs text-text-muted">Verifique também a caixa de spam.</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary font-medium mb-1 block">Código de verificação</label>
              <input ref={emailInputRef} type="text" inputMode="numeric" pattern="\d{6}" maxLength={6}
                required autoComplete="one-time-code"
                className="input-base text-center tracking-[0.5em] text-lg font-bold"
                placeholder="000000" value={emailCode}
                onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </div>
            <button type="submit" disabled={submitting || emailCode.length !== 6}
              className="btn-primary w-full flex items-center justify-center gap-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Verificar e-mail
            </button>
            <button type="button" disabled={resending} onClick={resendEmailOtp}
              className="w-full text-xs text-text-muted hover:text-accent-neon transition-colors flex items-center justify-center gap-1">
              {resending && <Loader2 className="w-3 h-3 animate-spin" />}
              Reenviar código
            </button>
          </form>
        )}

        {/* ─── Step 3: Profile info ─────────────────────────────────────── */}
        {step === 'profile_info' && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Sobre você</h2>
              <p className="text-sm text-text-secondary">Como devemos te chamar no app?</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome de exibição *</label>
              <input className="input-base" placeholder="Ex: João Silva"
                value={profile.display_name}
                onChange={(e) => updateProfile('display_name', e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Ano de nascimento</label>
                <input type="number" min={1900} max={new Date().getFullYear()}
                  className="input-base" placeholder="1990"
                  value={profile.birth_year}
                  onChange={(e) => updateProfile('birth_year', e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Gênero</label>
                <select className="input-base" value={profile.gender}
                  onChange={(e) => updateProfile('gender', e.target.value as 'M' | 'F' | '')}>
                  <option value="">—</option>
                  <option value="M">Masculino</option>
                  <option value="F">Feminino</option>
                </select>
              </div>
            </div>
            <button className="btn-primary w-full flex items-center justify-center gap-2"
              onClick={() => setStep('profile_location')} disabled={!profile.display_name}>
              Continuar <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ─── Step 4: Location ─────────────────────────────────────────── */}
        {step === 'profile_location' && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Onde você joga?</h2>
              <p className="text-sm text-text-secondary">Priorizamos torneios perto de você.</p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">UF</label>
                <select className="input-base" value={profile.home_state}
                  onChange={(e) => updateProfile('home_state', e.target.value)}>
                  {STATES.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
                <input className="input-base" placeholder="São Paulo" value={profile.home_city}
                  onChange={(e) => updateProfile('home_city', e.target.value)} />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">
                Raio de viagem: <span className="text-accent-neon font-semibold">{profile.travel_radius_km} km</span>
              </label>
              <input type="range" min={25} max={1000} step={25} value={profile.travel_radius_km}
                onChange={(e) => updateProfile('travel_radius_km', Number(e.target.value))}
                className="w-full accent-accent-neon" />
              <div className="flex justify-between text-[10px] text-text-muted mt-1">
                <span>25 km</span><span>1000 km</span>
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep('profile_info')}>Voltar</button>
              <button className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={() => setStep('profile_level')}>
                Continuar <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* ─── Step 5: Level ────────────────────────────────────────────── */}
        {step === 'profile_level' && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Seu nível</h2>
              <p className="text-sm text-text-secondary">Determina os torneios compatíveis com você.</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Tipo de jogador</label>
              <select className="input-base" value={profile.competitive_level}
                onChange={(e) => updateProfile('competitive_level', e.target.value)}>
                {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Classe (FPT / federação)</label>
              <div className="grid grid-cols-3 gap-2">
                {CLASSES.map((c) => (
                  <button key={c} type="button"
                    onClick={() => updateProfile('tennis_class', c === profile.tennis_class ? '' : c)}
                    className={`py-2.5 rounded-xl border text-sm font-semibold transition-colors ${
                      profile.tennis_class === c
                        ? 'bg-accent-neon text-bg-base border-accent-neon'
                        : 'bg-bg-card border-border text-text-primary hover:bg-bg-elevated'
                    }`}>
                    {c === 'PR' ? 'Principiante' : `${c}ª`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep('profile_location')}>Voltar</button>
              <button className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={onFinish} disabled={submitting}>
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                Concluir
              </button>
            </div>
          </div>
        )}

        {step === 'form' && (
          <div className="text-center mt-4 text-sm text-text-secondary">
            Já tem conta?{' '}
            <Link to="/login" className="text-accent-neon font-medium hover:underline">Entrar</Link>
          </div>
        )}
      </div>
    </div>
  );
};
