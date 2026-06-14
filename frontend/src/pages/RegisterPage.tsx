import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, CheckCircle, Check, Loader2, Mail, CreditCard,
  Users, User, Zap, FlaskConical, ShieldCheck,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { register, sendEmailOtp, verifyEmailOtp, createChildAccount } from '../services/auth';
import { createProfile } from '../services/data';
import { checkout, fetchPlans, Plan } from '../services/billing';
import { useAuth } from '../contexts/AuthContext';
import { extractApiError } from '../services/api';
import { User as UserType } from '../types';
import { LEVEL_LABELS, PASSWORD_HINT, validatePasswordRule } from '../utils/format';
import { loadCitiesForState } from '../components/StateMultiSelect';
import { FederationSelect } from '../components/FederationSelect';
import { MODALITY_OPTIONS, setProfileModality } from '../utils/profileModality';

// ─── Types ─────────────────────────────────────────────────────────────────────

type Step = 'plan' | 'form' | 'otp' | 'payment' | 'profile' | 'done_parent' | 'dependent';
type PlanSlug = 'tester' | 'free' | 'individual' | 'familia';

// ─── Password strength (igual ao mobile) ──────────────────────────────────────

function passwordStrength(pwd: string): { score: number; label: string; color: string } {
  if (!pwd) return { score: 0, label: '', color: 'transparent' };
  let score = 0;
  if (pwd.length >= 8)  score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  if (score <= 1) return { score, label: 'Fraca',    color: '#EF4444' };
  if (score <= 2) return { score, label: 'Razoável', color: '#FF6A00' };
  if (score <= 3) return { score, label: 'Boa',      color: '#3B82F6' };
  return { score, label: 'Forte', color: '#C6EF21' };
}

// ─── Plan metadata ─────────────────────────────────────────────────────────────

const PLAN_META: Record<PlanSlug, {
  label: string; price: string; description: string;
  icon: React.FC<{ className?: string }>;
}> = {
  tester:     { label: 'Tester (Beta)', price: 'Grátis',       description: 'Acesso completo durante o período beta. Todas as funcionalidades liberadas.', icon: (p) => <FlaskConical {...p} /> },
  free:       { label: 'Free',          price: 'Grátis',       description: 'Acesso básico. Consulte e explore torneios.', icon: (p) => <Zap {...p} /> },
  individual: { label: 'Individual',    price: 'R$ 19,90/mês', description: 'Alertas, agenda e filtros avançados para 1 jogador.', icon: (p) => <User {...p} /> },
  familia:    { label: 'Família',       price: 'R$ 34,90/mês', description: 'Até 4 perfis. Gerencie toda a família em uma conta.', icon: (p) => <Users {...p} /> },
};

const AVAILABLE_PLANS: PlanSlug[] = ['tester'];

const STATES = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

// ─── Component ─────────────────────────────────────────────────────────────────

export const RegisterPage: React.FC = () => {
  const nav = useNavigate();
  const { setUser, isAuthenticated } = useAuth();

  const [step, setStep] = useState<Step>('plan');
  const [registeredUser, setRegisteredUser] = useState<UserType | null>(null);
  const [duplicateEmail, setDuplicateEmail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const otpInputRef = useRef<HTMLInputElement>(null);

  // Plan
  const [planSlug, setPlanSlug] = useState<PlanSlug>('tester');
  const [apiPlans, setApiPlans] = useState<Plan[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(true);

  // Payment
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [pixCode, setPixCode] = useState('');
  const [pixQR, setPixQR] = useState('');
  const [pixCopied, setPixCopied] = useState(false);

  // Registration form
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    password: '',
    password_confirm: '',
    isResponsible: false,       // Sou pai/responsável — igual ao mobile
    accept_terms: false,
    marketing_consent: false,
  });

  // OTP
  const [otpCode, setOtpCode] = useState('');

  // Sports profile
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '' as 'M' | 'F' | '',
    home_state: 'SP',
    home_city: '',
    federation: null as number | null,
    competitive_level: 'pro',
    modality: '',
  });

  // IBGE cities
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  // Dependent form
  const [depForm, setDepForm] = useState({
    full_name: '', email: '', phone: '', password: '', password_confirm: '',
  });

  useEffect(() => {
    fetchPlans()
      .then(setApiPlans)
      .catch(() => {})
      .finally(() => setLoadingPlans(false));
  }, []);

  // Load cities when state changes (during profile step)
  useEffect(() => {
    if (step === 'profile') {
      setLoadingCities(true);
      loadCitiesForState(profile.home_state)
        .then(setCities)
        .finally(() => setLoadingCities(false));
    }
  }, [profile.home_state, step]);

  function isPlanAvailable(slug: PlanSlug) { return AVAILABLE_PLANS.includes(slug); }
  function isPaidPlan(slug: PlanSlug) { return slug === 'individual' || slug === 'familia'; }

  function getPlanPrice(slug: PlanSlug) {
    if (slug === 'tester' || slug === 'free') return 'Grátis';
    const p = apiPlans.find((pl) => pl.slug === (slug as any));
    if (p) return `R$ ${parseFloat(p.price_monthly).toFixed(2).replace('.', ',')} / mês`;
    return PLAN_META[slug].price;
  }

  // Role derived from plan + isResponsible (igual ao mobile)
  const role = ((planSlug === 'familia' || planSlug === 'tester') && form.isResponsible)
    ? 'parent' : 'player';

  // ─── Step: Register ────────────────────────────────────────────────────────
  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!form.full_name.trim()) { toast.error('Informe seu nome completo'); return; }
    if (!form.email.trim())     { toast.error('Informe seu e-mail'); return; }
    if (!form.password)         { toast.error('Defina uma senha'); return; }
    { const e = validatePasswordRule(form.password); if (e) { toast.error(e); return; } }
    if (form.password !== form.password_confirm) { toast.error('As senhas não conferem'); return; }
    if (!form.accept_terms) { toast.error('Aceite os termos para continuar'); return; }

    setSubmitting(true);
    try {
      const data = await register({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        password: form.password,
        password_confirm: form.password_confirm,
        role,
        accept_terms: form.accept_terms,
        marketing_consent: form.marketing_consent,
      });
      setRegisteredUser(data.user);
      setProfile((p) => ({ ...p, display_name: form.full_name.trim() }));
      if (data.email_otp_sent === false) {
        toast('Conta criada, mas não conseguimos enviar o código. Tente reenviar em instantes.');
      } else {
        toast.success('Conta criada! Verifique seu e-mail.');
      }
      setStep('otp');
      setTimeout(() => otpInputRef.current?.focus(), 100);
    } catch (err) {
      const msg = extractApiError(err);
      if (msg.toLowerCase().includes('email') && msg.toLowerCase().includes('existe')) {
        setDuplicateEmail(true);
      } else {
        toast.error(msg);
      }
    } finally { setSubmitting(false); }
  }

  // ─── Step: OTP ────────────────────────────────────────────────────────────
  async function onVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await verifyEmailOtp(otpCode.trim());
      toast.success('E-mail verificado!');

      if (planSlug === 'tester') {
        // Tester: cria assinatura em background, sem pagamento.
        // Usar 'tester' para que responsáveis possam cadastrar múltiplos dependentes
        // (tester tem max_members=4; 'individual' bloquearia o segundo dependente).
        checkout({ plan_slug: 'tester' as any, billing_period: 'monthly', payment_method: 'pix' }).catch(() => {});
        if (role === 'parent') {
          setStep('done_parent');
        } else {
          setStep('profile');
        }
      } else if (planSlug === 'free') {
        setStep('profile');
      } else {
        setStep('payment');
        startCheckout();
      }
    } catch (err) {
      toast.error(extractApiError(err));
    } finally { setSubmitting(false); }
  }

  // ─── Step: Payment ────────────────────────────────────────────────────────
  async function startCheckout() {
    setPaymentLoading(true);
    setPixCode(''); setPixQR('');
    try {
      const result = await checkout({
        plan_slug: planSlug as 'individual' | 'familia',
        billing_period: 'monthly',
        payment_method: 'pix',
      });
      if (result.pix?.copia_e_cola) {
        setPixCode(result.pix.copia_e_cola);
        setPixQR(result.pix.qr_code_image ?? '');
      } else {
        toast('Assinatura criada. Conclua o pagamento em "Minha assinatura".');
        proceedAfterPayment();
      }
    } catch {
      toast('Não foi possível gerar o PIX agora. Complete em "Minha assinatura" após entrar.');
      proceedAfterPayment();
    } finally { setPaymentLoading(false); }
  }

  function proceedAfterPayment() {
    if (role === 'parent') setStep('dependent');
    else setStep('profile');
  }

  function copyPix() {
    navigator.clipboard.writeText(pixCode).then(() => {
      setPixCopied(true);
      toast.success('Copiado!');
      setTimeout(() => setPixCopied(false), 3000);
    });
  }

  // ─── Step: Profile ────────────────────────────────────────────────────────
  async function onFinish() {
    setSubmitting(true);
    try {
      const created = await createProfile({
        display_name: profile.display_name || form.full_name || 'Jogador',
        birth_year: profile.birth_year ? Number(profile.birth_year) : null,
        gender: profile.gender || undefined,
        home_state: profile.home_state,
        home_city: profile.home_city,
        federation: profile.federation,
        competitive_level: profile.competitive_level as any,
        preferred_modality: profile.modality || '',
        is_primary: true,
      } as any);
      if (profile.modality && created?.id) setProfileModality(created.id, profile.modality);
      toast.success('Perfil criado! Bem-vindo ao Tenfy!');
      if (registeredUser) setUser(registeredUser);
      nav('/inicio', { replace: true });
    } catch (err) {
      const httpStatus = (err as any)?.response?.status;
      if (!httpStatus || httpStatus >= 500) {
        toast('Perfil não configurado. Complete em "Meu Perfil".');
        if (registeredUser) setUser(registeredUser);
        nav('/inicio', { replace: true });
      } else {
        toast.error(extractApiError(err));
      }
    } finally { setSubmitting(false); }
  }

  // ─── Step: Dependent ─────────────────────────────────────────────────────
  async function onCreateDependent() {
    if (!depForm.full_name.trim()) { toast.error('Informe o nome do dependente'); return; }
    if (!depForm.email.trim())     { toast.error('Informe o e-mail do dependente'); return; }
    if (!depForm.password)         { toast.error('Defina uma senha para o dependente'); return; }
    { const e = validatePasswordRule(depForm.password); if (e) { toast.error(e); return; } }
    if (depForm.password !== depForm.password_confirm) { toast.error('As senhas do dependente não conferem'); return; }
    setSubmitting(true);
    try {
      await createChildAccount({
        full_name: depForm.full_name.trim(),
        email: depForm.email.trim(),
        phone: depForm.phone.trim(),
        password: depForm.password,
        password_confirm: depForm.password_confirm,
      });
      toast.success('Dependente cadastrado! Bem-vindo ao Tenfy!');
      if (registeredUser) setUser(registeredUser);
      nav('/inicio', { replace: true });
    } catch (err) {
      toast.error(extractApiError(err));
    } finally { setSubmitting(false); }
  }

  async function resendOtp() {
    setResending(true);
    try { await sendEmailOtp(); toast.success('Novo código enviado.'); }
    catch { toast.error('Não foi possível reenviar.'); }
    finally { setResending(false); }
  }

  // Progress indicator
  const allSteps: Step[] = isPaidPlan(planSlug)
    ? ['plan', 'form', 'otp', 'payment', 'profile', 'done_parent', 'dependent']
    : ['plan', 'form', 'otp', 'profile', 'done_parent', 'dependent'];

  const visibleSteps: Step[] = role === 'parent'
    ? isPaidPlan(planSlug) ? ['plan', 'form', 'otp', 'payment', 'done_parent'] : ['plan', 'form', 'otp', 'done_parent']
    : isPaidPlan(planSlug) ? ['plan', 'form', 'otp', 'payment', 'profile'] : ['plan', 'form', 'otp', 'profile'];

  const STEP_LABELS: Record<Step, string> = {
    plan: 'Plano', form: 'Dados', otp: 'E-mail', payment: 'Pagamento',
    profile: 'Perfil', done_parent: 'Pronto', dependent: 'Dependente',
  };

  const stepIdx = visibleSteps.indexOf(step);
  const pwStrength = passwordStrength(form.password);

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex justify-center mb-6">
          <img src="/logos/logo_clara.png" alt="Tenfy" className="h-32 w-auto object-contain dark:hidden" />
          <img src="/logos/logo_escura.png" alt="Tenfy" className="h-16 w-auto object-contain hidden dark:block" />
        </div>
        <h1 className="text-xl font-bold text-center mb-5">Criar conta</h1>

        {/* Progress */}
        <div className="flex items-center justify-center gap-1 mb-6 flex-wrap">
          {visibleSteps.map((s, i) => (
            <React.Fragment key={s}>
              <div className="flex flex-col items-center gap-1">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                  i < stepIdx ? 'bg-accent-neon' : i === stepIdx ? 'bg-accent-neon ring-2 ring-accent-neon ring-offset-2 ring-offset-bg-base' : 'bg-bg-card text-text-muted border border-border-subtle'
                }`} style={{ color: i <= stepIdx ? 'rgb(var(--btn-text))' : undefined }}>
                  {i < stepIdx ? <CheckCircle className="w-3.5 h-3.5" /> : i + 1}
                </div>
                <span className="text-[10px] text-text-muted">{STEP_LABELS[s]}</span>
              </div>
              {i < visibleSteps.length - 1 && (
                <div className={`h-px w-4 mb-4 transition-colors ${i < stepIdx ? 'bg-accent-neon' : 'bg-border-subtle'}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* ─── PLAN ─────────────────────────────────────────────────────── */}
        {step === 'plan' && (
          <div className="card space-y-3">
            <div>
              <h2 className="text-lg font-bold">Escolha o plano</h2>
              <p className="text-xs text-text-muted mt-0.5">Pode fazer upgrade depois.</p>
            </div>
            {loadingPlans ? (
              <div className="py-6 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
            ) : (
              <div className="space-y-2">
                {/* Por hora exibe somente os planos disponíveis (AVAILABLE_PLANS = ['tester']);
                    os demais ficam ocultos (não removidos). Para reexibir, basta
                    voltar a listar os slugs aqui / em AVAILABLE_PLANS. */}
                {AVAILABLE_PLANS.map((slug) => {
                  const meta = PLAN_META[slug];
                  const available = isPlanAvailable(slug);
                  const selected = planSlug === slug && available;
                  const apiPlan = apiPlans.find((p) => p.slug === (slug as any));
                  return (
                    <button key={slug} type="button" disabled={!available}
                      onClick={() => available && setPlanSlug(slug)}
                      className={`w-full text-left p-4 rounded-xl border transition-all ${selected ? 'border-accent-neon bg-accent-neon/10' : available ? 'border-border-subtle bg-bg-card hover:border-accent-neon/40' : 'border-border-subtle bg-bg-card opacity-50 cursor-not-allowed'}`}>
                      <div className="flex items-start gap-3">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${selected ? 'bg-accent-neon/20' : 'bg-bg-elevated'}`}>
                          <meta.icon className={`w-4 h-4 ${selected ? 'text-accent-neon' : 'text-text-muted'}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`font-semibold text-sm ${selected ? 'text-accent-neon' : 'text-text-primary'}`}>{meta.label}</span>
                            <span className={`text-sm font-bold ${selected ? 'text-accent-neon' : 'text-text-secondary'}`}>{getPlanPrice(slug)}</span>
                            {!available ? (
                              <span className="text-[10px] font-bold text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">EM BREVE</span>
                            ) : slug === 'tester' ? (
                              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-accent-neon/20 text-accent-neon">PERÍODO BETA</span>
                            ) : apiPlan?.highlight_label ? (
                              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-accent-neon/20 text-accent-neon">{apiPlan.highlight_label.toUpperCase()}</span>
                            ) : null}
                          </div>
                          <p className="text-xs text-text-muted mt-0.5">{meta.description}</p>
                          {available && apiPlan && apiPlan.features.length > 0 && (
                            <div className="mt-1.5 space-y-0.5">
                              {apiPlan.features.slice(0, 3).map((f) => (
                                <div key={f.code} className="flex items-center gap-1 text-[11px] text-accent-neon">
                                  <Check className="w-3 h-3 shrink-0" />{f.name}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        {available && (
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 mt-1 ${selected ? 'border-accent-neon bg-accent-neon' : 'border-border-subtle'}`}
                            style={selected ? { color: 'rgb(var(--btn-text))' } : undefined}>
                            {selected && <Check className="w-3 h-3" />}
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
            <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={() => setStep('form')} disabled={loadingPlans}>
              Continuar <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ─── FORM ─────────────────────────────────────────────────────── */}
        {step === 'form' && (
          <form onSubmit={onRegister} className="card space-y-3">
            <p className="text-xs text-text-muted">
              Campos com <span className="text-red-400 font-bold">*</span> são obrigatórios.
            </p>

            {/* Plano badge */}
            {(() => { const PlanIcon = PLAN_META[planSlug].icon; return (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-accent-neon/10 border border-accent-neon/30">
              <PlanIcon className="w-3.5 h-3.5 text-accent-neon shrink-0" />
              <span className="text-xs font-bold text-accent-neon flex-1">Plano {PLAN_META[planSlug].label} — {getPlanPrice(planSlug)}</span>
              <button type="button" className="text-[11px] text-accent-neon underline" onClick={() => setStep('plan')}>Trocar</button>
            </div>
            ); })()}

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome completo *</label>
              <input className="input-base" placeholder="Ex: Maria Silva" value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">E-mail *</label>
              <input type="email" autoComplete="email"
                className={`input-base ${duplicateEmail ? 'border-red-500 focus:ring-red-500' : ''}`}
                placeholder="seu@email.com" value={form.email}
                onChange={(e) => { setForm({ ...form, email: e.target.value.trim() }); setDuplicateEmail(false); }} />
              {duplicateEmail && (
                <div className="mt-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400 space-y-1">
                  <p className="font-medium">Este e-mail já possui cadastro.</p>
                  <p><Link to="/login" className="underline text-accent-neon">Entrar</Link>{' '}ou{' '}<Link to="/recuperar-senha" className="underline text-accent-neon">recuperar senha</Link>.</p>
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Celular *</label>
              <input type="tel" autoComplete="tel" className="input-base" placeholder="11999999999"
                value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, '') })} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Senha *</label>
              <input type="password" autoComplete="new-password" className="input-base"
                placeholder="Mínimo 8 caracteres" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <p className="text-[11px] text-text-muted mt-1">{PASSWORD_HINT}</p>
              {form.password.length > 0 && (
                <div className="mt-1.5 space-y-1">
                  <div className="flex gap-1">
                    {[1,2,3,4,5].map((i) => (
                      <div key={i} className="flex-1 h-1 rounded-full transition-colors"
                        style={{ backgroundColor: i <= pwStrength.score ? pwStrength.color : 'rgb(var(--border-subtle))' }} />
                    ))}
                  </div>
                  <p className="text-[11px]" style={{ color: pwStrength.color }}>{pwStrength.label}</p>
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Confirme a senha *</label>
              <input type="password" autoComplete="new-password" className="input-base"
                placeholder="Repita a senha" value={form.password_confirm}
                onChange={(e) => setForm({ ...form, password_confirm: e.target.value })} />
            </div>

            {/* Sou pai/responsável — só aparece para tester e família, igual ao mobile */}
            {(planSlug === 'familia' || planSlug === 'tester') && (
              <div className="border-t border-border-subtle pt-3">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox" className="mt-0.5 accent-accent-neon shrink-0 w-4 h-4"
                    checked={form.isResponsible} onChange={(e) => setForm({ ...form, isResponsible: e.target.checked })} />
                  <div>
                    <span className="text-sm font-medium text-text-primary">Sou pai / responsável (não sou o jogador)</span>
                    <p className="text-xs text-text-muted mt-0.5">Marque se vai gerenciar o perfil de dependentes, como filho(a) ou atleta.</p>
                  </div>
                </label>
              </div>
            )}

            <div className="border-t border-border-subtle pt-3 space-y-2">
              <label className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" className="mt-0.5 accent-accent-neon shrink-0 w-4 h-4"
                  checked={form.accept_terms} onChange={(e) => setForm({ ...form, accept_terms: e.target.checked })} />
                <div>
                  <span className="text-xs text-text-secondary">Aceito os Termos de Uso e Política de Privacidade (LGPD) *</span>
                  <br />
                  <a href="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"
                    target="_blank" rel="noopener noreferrer" className="text-xs text-accent-neon underline">
                    Ler Termos e Política de Privacidade
                  </a>
                </div>
              </label>
              <label className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" className="mt-0.5 accent-accent-neon shrink-0 w-4 h-4"
                  checked={form.marketing_consent} onChange={(e) => setForm({ ...form, marketing_consent: e.target.checked })} />
                <span className="text-xs text-text-secondary">Desejo receber novidades e comunicações por e-mail (opcional)</span>
              </label>
            </div>

            <div className="flex gap-2 pt-1">
              <button type="button" className="btn-secondary flex-1" onClick={() => setStep('plan')}>Voltar</button>
              <button type="submit" disabled={submitting} className="btn-primary flex-1 flex items-center justify-center gap-2">
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Criar conta
              </button>
            </div>
          </form>
        )}

        {/* ─── OTP ──────────────────────────────────────────────────────── */}
        {step === 'otp' && (
          <form onSubmit={onVerifyOtp} className="card space-y-4">
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
              <input ref={otpInputRef} type="text" inputMode="numeric" pattern="\d{6}" maxLength={6}
                required autoComplete="one-time-code"
                className="input-base text-center tracking-[0.5em] text-lg font-bold"
                placeholder="000000" value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </div>
            <button type="submit" disabled={submitting || otpCode.length !== 6} className="btn-primary w-full flex items-center justify-center gap-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Confirmar e-mail
            </button>
            <button type="button" disabled={resending} onClick={resendOtp}
              className="w-full text-xs text-text-muted hover:text-accent-neon flex items-center justify-center gap-1 transition-colors">
              {resending && <Loader2 className="w-3 h-3 animate-spin" />}
              Reenviar código
            </button>
          </form>
        )}

        {/* ─── PAYMENT ─────────────────────────────────────────────────── */}
        {step === 'payment' && (
          <div className="card space-y-4">
            <div className="flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-accent-neon" />
              <h2 className="font-semibold">Ativar Plano {PLAN_META[planSlug].label}</h2>
            </div>
            {paymentLoading ? (
              <div className="py-8 flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
                <p className="text-sm text-text-muted">Gerando cobrança PIX...</p>
              </div>
            ) : pixCode ? (
              <>
                <p className="text-sm text-text-secondary">Escaneie o QR Code ou copie o código Pix para pagar {getPlanPrice(planSlug)}.</p>
                {pixQR && <div className="flex justify-center"><img src={pixQR.startsWith('data:') ? pixQR : `data:image/png;base64,${pixQR}`} alt="QR Code Pix" className="w-40 h-40 rounded border border-border-subtle" /></div>}
                <div>
                  <p className="text-xs text-text-muted mb-1">Pix copia e cola</p>
                  <div className="flex gap-1">
                    <input className="input-base text-xs flex-1" readOnly value={pixCode} />
                    <button type="button" className="btn-secondary !text-xs whitespace-nowrap" onClick={copyPix}>
                      {pixCopied ? 'Copiado!' : 'Copiar código'}
                    </button>
                  </div>
                </div>
                <div className="rounded-lg bg-accent-neon/8 border border-accent-neon/20 p-3">
                  <p className="text-xs text-text-muted">Após o pagamento, o plano será ativado automaticamente. Clique em "Já paguei" para continuar.</p>
                </div>
                <button className="btn-primary w-full" onClick={proceedAfterPayment}>Já paguei — continuar</button>
                <button className="w-full text-xs text-text-muted hover:text-text-secondary text-center"
                  onClick={() => { if (registeredUser) setUser(registeredUser); nav('/inicio', { replace: true }); }}>
                  Pagar depois (entrar no app)
                </button>
              </>
            ) : (
              <>
                <p className="text-sm text-text-secondary">Não foi possível gerar o PIX. Complete em "Minha assinatura" após entrar.</p>
                <button className="btn-primary w-full" onClick={proceedAfterPayment}>Continuar cadastro</button>
              </>
            )}
          </div>
        )}

        {/* ─── DONE PARENT (tester responsável) ─────────────────────────── */}
        {step === 'done_parent' && (
          <div className="card space-y-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-accent-neon" />
              <h2 className="font-semibold">Conta criada!</h2>
            </div>
            <p className="text-sm text-text-secondary">Sua conta de responsável foi criada com sucesso.</p>
            <div className="rounded-xl bg-accent-blue/10 border border-accent-blue/30 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full bg-accent-blue/30 flex items-center justify-center shrink-0">
                  <span className="text-accent-blue text-[10px] font-bold">i</span>
                </div>
                <p className="text-sm font-bold text-accent-blue">Como adicionar dependentes</p>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                1. Acesse a aba <strong>Perfil</strong><br />
                2. Na seção <strong>Perfis esportivos</strong>, toque em <strong>Adicionar perfil</strong><br />
                3. Preencha os dados do seu filho ou dependente
              </p>
            </div>
            <button className="btn-primary w-full" onClick={() => { if (registeredUser) setUser(registeredUser); nav('/inicio', { replace: true }); }}>
              Ir para o painel
            </button>
          </div>
        )}

        {/* ─── DEPENDENT (família responsável) ──────────────────────────── */}
        {step === 'dependent' && (
          <div className="card space-y-3">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-accent-neon" />
              <h2 className="font-semibold">Cadastrar dependente</h2>
            </div>
            <p className="text-sm text-text-secondary">
              Crie a conta do seu dependente. Depois ele poderá entrar com este e-mail e senha para preencher seu perfil esportivo.
            </p>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome completo *</label>
              <input className="input-base" placeholder="Ex: Pedro Silva" value={depForm.full_name}
                onChange={(e) => setDepForm({ ...depForm, full_name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">E-mail *</label>
              <input type="email" className="input-base" placeholder="dependente@email.com" value={depForm.email}
                onChange={(e) => setDepForm({ ...depForm, email: e.target.value.trim() })} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Celular (opcional)</label>
              <input type="tel" className="input-base" placeholder="Opcional" value={depForm.phone}
                onChange={(e) => setDepForm({ ...depForm, phone: e.target.value.replace(/\D/g, '') })} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Senha *</label>
              <input type="password" className="input-base" placeholder="Mínimo 8 caracteres" value={depForm.password}
                onChange={(e) => setDepForm({ ...depForm, password: e.target.value })} />
              <p className="text-[11px] text-text-muted mt-1">{PASSWORD_HINT}</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Confirme a senha *</label>
              <input type="password" className="input-base" placeholder="Repita a senha" value={depForm.password_confirm}
                onChange={(e) => setDepForm({ ...depForm, password_confirm: e.target.value })} />
            </div>
            <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={onCreateDependent} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Cadastrar dependente
            </button>
            <button className="w-full text-xs text-text-muted hover:text-text-secondary text-center"
              onClick={() => { if (registeredUser) setUser(registeredUser); nav('/inicio', { replace: true }); }}>
              Pular por enquanto
            </button>
          </div>
        )}

        {/* ─── PROFILE ──────────────────────────────────────────────────── */}
        {step === 'profile' && (
          <div className="card space-y-3">
            <div className="rounded-xl bg-accent-neon/10 border border-accent-neon/30 px-4 py-3 flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-accent-neon mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-bold text-accent-neon">Conta criada com sucesso!</p>
                <p className="text-xs text-text-secondary mt-0.5">Preencha seu perfil esportivo para encontrar torneios compatíveis. Você pode pular e configurar depois no painel.</p>
              </div>
            </div>
            <div>
              <h2 className="text-xl font-bold mb-0.5">Perfil esportivo</h2>
              <p className="text-sm text-text-secondary">Dados usados para recomendar torneios compatíveis com você.</p>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome de exibição</label>
              <input className="input-base" placeholder="Ex: João Silva"
                value={profile.display_name}
                onChange={(e) => setProfile({ ...profile, display_name: e.target.value })} />
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Ano de nascimento</label>
              <input type="number" min={1900} max={new Date().getFullYear()}
                className="input-base" placeholder="Ex: 2008"
                value={profile.birth_year}
                onChange={(e) => setProfile({ ...profile, birth_year: e.target.value })} />
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Gênero</label>
              <select className="input-base" value={profile.gender}
                onChange={(e) => setProfile({ ...profile, gender: e.target.value as 'M' | 'F' | '' })}>
                <option value="">Selecione...</option>
                <option value="M">Masculino</option>
                <option value="F">Feminino</option>
              </select>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Estado (UF)</label>
                <select className="input-base" value={profile.home_state}
                  onChange={(e) => setProfile({ ...profile, home_state: e.target.value, home_city: '' })}>
                  {STATES.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
                {cities.length > 0 ? (
                  <select className="input-base" value={profile.home_city}
                    onChange={(e) => setProfile({ ...profile, home_city: e.target.value })}>
                    <option value="">{loadingCities ? 'Carregando...' : 'Selecione a cidade'}</option>
                    {cities.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                ) : (
                  <input className="input-base" placeholder={loadingCities ? 'Carregando...' : 'Cidade'} value={profile.home_city}
                    onChange={(e) => setProfile({ ...profile, home_city: e.target.value })} />
                )}
              </div>
            </div>

            {/* Federação — substituiu a multisseleção de estados */}
            <FederationSelect
              value={profile.federation}
              onChange={(id) => setProfile((p) => ({ ...p, federation: id }))}
            />

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Modalidade principal</label>
              <select className="input-base" value={profile.modality}
                onChange={(e) => setProfile({ ...profile, modality: e.target.value })}>
                {MODALITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nível competitivo</label>
              <select className="input-base" value={profile.competitive_level}
                onChange={(e) => setProfile({ ...profile, competitive_level: e.target.value })}>
                {Object.entries(LEVEL_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            <button className="btn-primary w-full flex items-center justify-center gap-2" onClick={onFinish} disabled={submitting}>
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              Finalizar cadastro
            </button>
            <button className="w-full text-xs text-text-muted hover:text-text-secondary text-center"
              onClick={() => { if (registeredUser) setUser(registeredUser); nav('/inicio', { replace: true }); }}>
              Pular (configurar depois)
            </button>
          </div>
        )}

        {(step === 'plan' || step === 'form') && (
          <div className="text-center mt-4 text-sm text-text-secondary">
            Já possui conta?{' '}
            <button
              type="button"
              className="text-accent-neon font-medium hover:underline"
              onClick={() => nav(isAuthenticated ? '/inicio' : '/login')}
            >
              Entrar
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
