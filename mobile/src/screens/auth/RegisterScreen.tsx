import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, Share, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { AuthStackParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { createProfile, linkUtr, searchUtr } from '../../services/data';
import { extractApiError, storage } from '../../services/api';
import { markProfileDirty } from '../../utils/profileRefresh';
import { createChildAccount, register, sendEmailOtp, verifyEmailOtp } from '../../services/auth';
import { checkout, fetchPlans, Plan } from '../../services/billing';
import { UtrCandidate, User } from '../../types';
import { LEVEL_LABELS, TENNIS_CLASS_LABELS } from '../../utils/format';
import { MODALITY_OPTIONS, setProfileModality } from '../../utils/profileModality';
import { AppText, Button, Card, Checkbox, Input, Screen, SelectField } from '../../components/ui';
import { FederationSelect } from '../../components/FederationSelect';

type AppColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

function passwordStrength(pwd: string, c: AppColors): { score: number; label: string; color: string } {
  if (!pwd) return { score: 0, label: '', color: 'transparent' };
  let score = 0;
  if (pwd.length >= 8)  score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  if (score <= 1) return { score, label: 'Fraca',    color: c.danger };
  if (score <= 2) return { score, label: 'Razoável', color: c.statusClosing };
  if (score <= 3) return { score, label: 'Boa',      color: c.accentBlue };
  return { score, label: 'Forte', color: c.statusOpen };
}

type Props = NativeStackScreenProps<AuthStackParamList, 'Register'>;
type Step = 'plan' | 'form' | 'otp' | 'payment' | 'profile' | 'utr' | 'dependent' | 'done_parent';
type PlanSlug = 'free' | 'individual' | 'familia' | 'tester';

// Hardcoded fallback shown while API loads or if it fails
const PLAN_FALLBACK: Record<string, { label: string; price: string; description: string; icon: string }> = {
  tester:     { label: 'Tester (Beta)', price: 'Grátis',       description: 'Acesso completo durante o período beta. Todas as funcionalidades liberadas.', icon: 'flask-outline' },
  free:       { label: 'Free',          price: 'Grátis',       description: 'Acesso básico. Consulte e explore torneios.', icon: 'search-outline' },
  individual: { label: 'Individual',    price: 'R$ 19,90/mês', description: 'Alertas, agenda, filtros avançados e suporte prioritário.', icon: 'person-outline' },
  familia:    { label: 'Família',       price: 'R$ 34,90/mês', description: 'Até 4 perfis. Gerencie toda a família em uma conta.', icon: 'people-outline' },
};

const UF_OPTIONS = [
  { value: 'AC', label: 'AC - Acre' }, { value: 'AL', label: 'AL - Alagoas' },
  { value: 'AP', label: 'AP - Amapa' }, { value: 'AM', label: 'AM - Amazonas' },
  { value: 'BA', label: 'BA - Bahia' }, { value: 'CE', label: 'CE - Ceara' },
  { value: 'DF', label: 'DF - Distrito Federal' }, { value: 'ES', label: 'ES - Espirito Santo' },
  { value: 'GO', label: 'GO - Goias' }, { value: 'MA', label: 'MA - Maranhao' },
  { value: 'MT', label: 'MT - Mato Grosso' }, { value: 'MS', label: 'MS - Mato Grosso do Sul' },
  { value: 'MG', label: 'MG - Minas Gerais' }, { value: 'PA', label: 'PA - Para' },
  { value: 'PB', label: 'PB - Paraiba' }, { value: 'PR', label: 'PR - Parana' },
  { value: 'PE', label: 'PE - Pernambuco' }, { value: 'PI', label: 'PI - Piaui' },
  { value: 'RJ', label: 'RJ - Rio de Janeiro' }, { value: 'RN', label: 'RN - Rio Grande do Norte' },
  { value: 'RS', label: 'RS - Rio Grande do Sul' }, { value: 'RO', label: 'RO - Rondonia' },
  { value: 'RR', label: 'RR - Roraima' }, { value: 'SC', label: 'SC - Santa Catarina' },
  { value: 'SP', label: 'SP - Sao Paulo' }, { value: 'SE', label: 'SE - Sergipe' },
  { value: 'TO', label: 'TO - Tocantins' },
];
const LEVEL_OPTIONS = Object.entries(LEVEL_LABELS).map(([value, label]) => ({ value, label }));
const CLASS_OPTIONS = [
  { value: '', label: 'Sem classe definida' },
  ...Object.entries(TENNIS_CLASS_LABELS).map(([value, label]) => ({ value, label })),
];
const MOBILE_MODALITY_OPTIONS = MODALITY_OPTIONS.map(({ value, label }) => ({ value, label }));
const GENDER_OPTIONS = [{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }];

export function RegisterScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const { setUser } = useAuth();

  // ── Plan selection state ─────────────────────────────────────────────────────
  const [planSlug, setPlanSlug]       = useState<PlanSlug>('tester');
  const [apiPlans, setApiPlans]       = useState<Plan[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(true);

  // Plan object from API for Individual/Família (used for checkout)
  const selectedApiPlan = apiPlans.find((p) => p.slug === planSlug) ?? null;

  // ── Registration state ───────────────────────────────────────────────────────
  const [step, setStep]               = useState<Step>('plan');
  const [registeredUser, setRegisteredUser] = useState<User | null>(null);
  const [submitting, setSubmitting]   = useState(false);
  const [resending, setResending]     = useState(false);

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    password: '',
    password_confirm: '',
    // role determined by plan: free/individual → player, familia → player or parent
    isResponsible: false,   // for Família only: am I the account responsible?
    accept_terms: false,
    marketing_consent: false,
  });
  const [emailCode, setEmailCode] = useState('');
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '',
    home_state: 'SP',
    home_city: '',
    federation: null as number | null,
    competitive_level: 'amateur',
    tennis_class: '',
    modality: '',
  });

  const [dependentForm, setDependentForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    password: '',
    password_confirm: '',
  });
  const [cities, setCities]     = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  // ── UTR state ────────────────────────────────────────────────────────────────
  const [utrCandidates, setUtrCandidates] = useState<UtrCandidate[]>([]);
  const [utrSearching, setUtrSearching] = useState(false);
  const [utrLinking, setUtrLinking] = useState(false);
  const [createdProfileId, setCreatedProfileId] = useState<number | null>(null);

  // ── Payment state ────────────────────────────────────────────────────────────
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [pixCode, setPixCode]     = useState('');
  const [pixQR, setPixQR]         = useState('');
  const [pixCopied, setPixCopied] = useState(false);
  const copyTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load plans from API (public endpoint — no auth needed) ───────────────────
  useEffect(() => {
    const timeout = new Promise<Plan[]>((_, reject) =>
      setTimeout(() => reject(new Error('timeout')), 8000)
    );
    Promise.race([fetchPlans(), timeout])
      .then(setApiPlans)
      .catch(() => {})
      .finally(() => setLoadingPlans(false));
  }, []);

  // ── Load cities when state changes ───────────────────────────────────────────
  useEffect(() => {
    if (step === 'profile') loadCities(profile.home_state);
  }, [profile.home_state, step]);

  async function loadCities(uf: string) {
    if (!uf) return;
    setLoadingCities(true);
    try {
      const res = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/estados/${uf}/municipios`);
      const data: any[] = await res.json();
      setCities(data.map((c) => ({ value: c.nome, label: c.nome })).sort((a, b) => a.label.localeCompare(b.label, 'pt-BR')));
    } catch { setCities([]); }
    finally { setLoadingCities(false); }
  }

  // Derived role from plan + isResponsible flag
  const role = ((planSlug === 'familia' || planSlug === 'tester') && form.isResponsible) ? 'parent' : 'player';

  // ── Step handlers ─────────────────────────────────────────────────────────────

  async function onRegister() {
    if (!form.full_name.trim()) return Toast.show({ type: 'error', text1: 'Informe seu nome completo' });
    if (!form.email.trim())     return Toast.show({ type: 'error', text1: 'Informe seu e-mail' });
    if (!form.phone.trim())     return Toast.show({ type: 'error', text1: 'Informe seu celular' });
    if (!form.password)         return Toast.show({ type: 'error', text1: 'Defina uma senha' });
    if (form.password.length < 8) return Toast.show({ type: 'error', text1: 'Senha precisa ter no minimo 8 caracteres' });
    if (form.password !== form.password_confirm) return Toast.show({ type: 'error', text1: 'As senhas nao conferem' });
    if (!form.accept_terms)     return Toast.show({ type: 'error', text1: 'Aceite os termos para continuar' });
    setSubmitting(true);
    try {
      const data = await register({
        full_name: form.full_name,
        email: form.email,
        phone: form.phone,
        password: form.password,
        password_confirm: form.password_confirm,
        role,
        accept_terms: form.accept_terms,
        marketing_consent: form.marketing_consent,
      });
      setRegisteredUser(data.user);
      setProfile((p) => ({ ...p, display_name: form.full_name }));
      setStep('otp');
      if (data.email_otp_sent === false) {
        Toast.show({ type: 'info', text1: 'Conta criada', text2: 'Nao conseguimos enviar o codigo agora. Tente reenviar em instantes.' });
      } else {
        Toast.show({ type: 'success', text1: 'Conta criada! Verifique seu e-mail.' });
      }
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar conta', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function onVerify() {
    setSubmitting(true);
    try {
      await verifyEmailOtp(emailCode.trim());
      Toast.show({ type: 'success', text1: 'E-mail verificado!' });
      if (planSlug === 'tester') {
        // Tester: create subscription in background (no payment), go to profile or parent done
        checkout({ plan_slug: 'tester', billing_period: 'monthly', payment_method: 'pix' }).catch(() => {});
        if (role === 'parent') {
          setStep('done_parent');
        } else {
          setStep('profile');
        }
      } else if (planSlug === 'free') {
        // Free: skip payment, go to profile
        setStep('profile');
      } else {
        // Paid: show payment step and immediately start checkout
        setStep('payment');
        startCheckout();
      }
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro na verificacao', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function startCheckout() {
    if (!selectedApiPlan) {
      // API plans not loaded yet — proceed without payment
      Toast.show({ type: 'info', text1: 'Planos indisponíveis agora. Configure sua assinatura em Minha assinatura.' });
      setStep('profile');
      return;
    }
    setPaymentLoading(true);
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
        // Asaas not configured or no PIX code — let user proceed
        Toast.show({ type: 'info', text1: 'Assinatura criada. Conclua o pagamento em Minha assinatura.' });
        proceedAfterPayment();
      }
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar assinatura', text2: extractApiError(err) });
      // Allow proceeding even if checkout fails (don't block registration)
    } finally {
      setPaymentLoading(false);
    }
  }

  function proceedAfterPayment() {
    if (role === 'parent') {
      setStep('dependent');
    } else {
      setStep('profile');
    }
  }

  async function onFinish() {
    setSubmitting(true);
    try {
      const created = await createProfile({
        display_name: profile.display_name || form.full_name || 'Jogador',
        birth_year: profile.birth_year ? Number(profile.birth_year) : null,
        gender: (profile.gender || undefined) as any,
        home_state: profile.home_state,
        home_city: profile.home_city,
        federation: profile.federation,
        competitive_level: profile.competitive_level as any,
        tennis_class: profile.tennis_class || '',
        preferred_modality: profile.modality || '',
        is_primary: true,
      } as any);
      if (profile.modality && created?.id) await setProfileModality(created.id, profile.modality);
      markProfileDirty();
      await storage.set('th_just_registered', '1');

      if (created?.id) {
        setCreatedProfileId(created.id);
        setStep('utr');
        // Start UTR search in background — non-blocking
        _searchUtrForProfile(created.id, profile.display_name || form.full_name || '');
      } else {
        if (registeredUser) setUser(registeredUser);
        Toast.show({ type: 'success', text1: 'Perfil criado! Bem-vindo!' });
      }
    } catch (err: any) {
      const httpStatus: number | undefined = err?.response?.status;
      const isServerOrNetwork = !httpStatus || httpStatus >= 500;
      if (isServerOrNetwork) {
        Toast.show({
          type: 'info',
          text1: 'Perfil não configurado',
          text2: 'Complete seu perfil em "Meu Perfil" para encontrar torneios compatíveis.',
          visibilityTime: 6000,
        });
        if (registeredUser) setUser(registeredUser);
      } else {
        Toast.show({ type: 'error', text1: 'Erro ao finalizar cadastro', text2: extractApiError(err), visibilityTime: 5000 });
      }
    } finally { setSubmitting(false); }
  }

  async function _searchUtrForProfile(profileId: number, name: string) {
    if (!name.trim() || name.trim().length < 2) return;
    setUtrSearching(true);
    setUtrCandidates([]);
    try {
      const result = await searchUtr(profileId, name.trim());
      setUtrCandidates((result.candidates ?? []).slice(0, 3));
    } catch {
      // Silently fail — user continues normally without UTR
    } finally {
      setUtrSearching(false);
    }
  }

  function _finishAfterUtr() {
    if (registeredUser) setUser(registeredUser);
    Toast.show({ type: 'success', text1: 'Bem-vindo!' });
  }

  async function _onSelectUtrCandidate(candidate: UtrCandidate) {
    if (!createdProfileId || utrLinking) return;
    setUtrLinking(true);
    try {
      await linkUtr(createdProfileId, candidate);
    } catch {
      // Non-blocking — proceed even if linking fails
    } finally {
      setUtrLinking(false);
      _finishAfterUtr();
    }
  }

  async function onCreateDependent() {
    if (!dependentForm.full_name.trim()) return Toast.show({ type: 'error', text1: 'Informe o nome completo do dependente' });
    if (!dependentForm.email.trim())     return Toast.show({ type: 'error', text1: 'Informe o e-mail do dependente' });
    if (!dependentForm.password)         return Toast.show({ type: 'error', text1: 'Defina uma senha para o dependente' });
    if (dependentForm.password.length < 8) return Toast.show({ type: 'error', text1: 'A senha precisa ter no minimo 8 caracteres' });
    if (dependentForm.password !== dependentForm.password_confirm) return Toast.show({ type: 'error', text1: 'As senhas do dependente nao conferem' });
    setSubmitting(true);
    try {
      await createChildAccount({
        full_name: dependentForm.full_name.trim(),
        email: dependentForm.email.trim(),
        phone: dependentForm.phone.trim(),
        password: dependentForm.password,
        password_confirm: dependentForm.password_confirm,
      });
      if (registeredUser) setUser(registeredUser);
      Toast.show({ type: 'success', text1: 'Dependente cadastrado!', text2: 'Ele ja pode entrar e completar o perfil esportivo.' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao cadastrar dependente', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function resendOtp() {
    setResending(true);
    try { await sendEmailOtp(); Toast.show({ type: 'success', text1: 'Novo codigo enviado.' }); }
    catch { Toast.show({ type: 'error', text1: 'Nao foi possivel reenviar.' }); }
    finally { setResending(false); }
  }

  async function copyPixCode() {
    if (!pixCode) return;
    try {
      await Share.share({ message: pixCode });
      setPixCopied(true);
      if (copyTimeout.current) clearTimeout(copyTimeout.current);
      copyTimeout.current = setTimeout(() => setPixCopied(false), 3000);
    } catch {
      // User dismissed share sheet — no action needed
    }
  }

  // ── Plan info helpers ─────────────────────────────────────────────────────────
  function getPlanPrice(slug: PlanSlug): string {
    if (slug === 'free' || slug === 'tester') return 'Grátis';
    const p = apiPlans.find((pl) => pl.slug === slug);
    if (p) return `R$ ${parseFloat(p.price_monthly).toFixed(2).replace('.', ',')} / mês`;
    return PLAN_FALLBACK[slug]?.price ?? '';
  }

  function isPlanAvailable(slug: PlanSlug): boolean {
    const apiPlan = apiPlans.find((p) => p.slug === slug);
    if (apiPlan?.is_available !== undefined) return apiPlan.is_available;
    return slug === 'tester';
  }

  const PLAN_SLUGS: PlanSlug[] = ['tester', 'free', 'individual', 'familia'];

  return (
    <Screen>
      <View style={{ alignItems: 'center', marginBottom: 8, marginTop: 8 }}>
        <Image
          source={require('../../../assets/logo2.png')}
          style={{ width: 200, height: 64 }}
          resizeMode="contain"
        />
      </View>
      <Card>
        <AppText variant="section">Criar conta</AppText>

        {/* ── Step: Plan selection ─────────────────────────────────────────── */}
        {step === 'plan' ? (
          <>
            <AppText variant="muted" style={{ marginBottom: 12 }}>
              Escolha o plano. Pode fazer upgrade depois.
            </AppText>

            {loadingPlans ? (
              <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                <ActivityIndicator color={colors.accentNeon} />
              </View>
            ) : (
              PLAN_SLUGS.map((slug) => {
                const available = isPlanAvailable(slug);
                const isUnavailable = !available;
                const selected = planSlug === slug && available;
                const info = PLAN_FALLBACK[slug];
                const apiPlan = apiPlans.find((p) => p.slug === slug);
                const price = getPlanPrice(slug);
                return (
                  <Pressable
                    key={slug}
                    onPress={isUnavailable ? undefined : () => setPlanSlug(slug)}
                    style={{
                      flexDirection: 'row', alignItems: 'flex-start', gap: 12,
                      padding: 14, borderRadius: 14, marginBottom: 10,
                      borderWidth: selected ? 2 : 1,
                      borderColor: selected ? colors.accentNeon : colors.borderSubtle,
                      backgroundColor: isUnavailable ? `${colors.borderSubtle}22` : selected ? `${colors.accentNeon}10` : colors.bgBase,
                      opacity: isUnavailable ? 0.55 : 1,
                    }}
                  >
                    <View style={{
                      width: 40, height: 40, borderRadius: 20,
                      backgroundColor: selected ? `${colors.accentNeon}22` : `${colors.borderSubtle}55`,
                      alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>
                      <Ionicons name={info.icon as any} size={20} color={selected ? colors.accentNeon : colors.textMuted} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <AppText variant="body" style={{ fontWeight: '700', color: selected ? colors.accentNeon : colors.textPrimary }}>
                          {info.label}
                        </AppText>
                        <AppText style={{ fontSize: 14, fontWeight: '800', color: selected ? colors.accentNeon : colors.textSecondary }}>
                          {price}
                        </AppText>
                        {isUnavailable ? (
                          <View style={{ backgroundColor: `${colors.textMuted}22`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
                            <AppText variant="caption" style={{ color: colors.textMuted, fontWeight: '700', fontSize: 10 }}>
                              EM BREVE
                            </AppText>
                          </View>
                        ) : apiPlan?.highlight_label ? (
                          <View style={{ backgroundColor: `${colors.accentNeon}22`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
                            <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 10 }}>
                              {apiPlan.highlight_label.toUpperCase()}
                            </AppText>
                          </View>
                        ) : null}
                      </View>
                      <AppText variant="muted" style={{ marginTop: 3, fontSize: 12 }}>{info.description}</AppText>
                      {apiPlan && available ? (
                        <View style={{ marginTop: 4, gap: 2 }}>
                          {apiPlan.features.slice(0, 3).map((f) => (
                            <View key={f.code} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <Ionicons name="checkmark" size={11} color={colors.accentNeon} />
                              <AppText variant="caption" style={{ fontSize: 10, color: colors.textMuted }}>{f.name}</AppText>
                            </View>
                          ))}
                        </View>
                      ) : null}
                    </View>
                    {available && selected ? (
                      <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                        <Ionicons name="checkmark" size={13} color={colors.bgBase} />
                      </View>
                    ) : available ? (
                      <View style={{ width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: colors.borderSubtle, flexShrink: 0, marginTop: 2 }} />
                    ) : null}
                  </Pressable>
                );
              })
            )}

            <Button title="Continuar" onPress={() => setStep('form')} disabled={loadingPlans || !isPlanAvailable(planSlug)} />
          </>
        ) : null}

        {/* ── Step: Registration form ──────────────────────────────────────── */}
        {step === 'form' ? (
          <>
            <AppText variant="muted" style={{ marginBottom: 4 }}>
              Campos com <AppText variant="muted" style={{ color: colors.danger, fontWeight: '700' }}>*</AppText> são obrigatorios.
            </AppText>

            {/* Show selected plan as a read-only badge */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 12, backgroundColor: `${colors.accentNeon}10`, borderWidth: 1, borderColor: `${colors.accentNeon}33`, marginBottom: 4 }}>
              <Ionicons name={PLAN_FALLBACK[planSlug].icon as any} size={16} color={colors.accentNeon} />
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>
                Plano {PLAN_FALLBACK[planSlug].label} — {getPlanPrice(planSlug)}
              </AppText>
              <Pressable onPress={() => setStep('plan')} style={{ marginLeft: 'auto' }}>
                <AppText variant="caption" style={{ color: colors.accentNeon, textDecorationLine: 'underline', fontSize: 11 }}>Trocar</AppText>
              </Pressable>
            </View>

            <Input label="Nome completo" required value={form.full_name} onChangeText={(v) => setForm({ ...form, full_name: v })} autoCapitalize="words" placeholder="Ex: Maria Silva" />
            <Input label="E-mail" required value={form.email} onChangeText={(v) => setForm({ ...form, email: v.trim() })} autoCapitalize="none" keyboardType="email-address" placeholder="seu@email.com" />
            <Input label="Celular" required value={form.phone} onChangeText={(v) => setForm({ ...form, phone: v.replace(/\D/g, '') })} keyboardType="phone-pad" placeholder="11999999999" />
            <Input label="Senha" required value={form.password} onChangeText={(v) => setForm({ ...form, password: v })} secureTextEntry placeholder="Minimo 8 caracteres" />
            {form.password.length > 0 && (() => {
              const { score, label, color } = passwordStrength(form.password, colors);
              return (
                <View style={{ marginTop: -8, marginBottom: 4, gap: 4 }}>
                  <View style={{ flexDirection: 'row', gap: 4 }}>
                    {[1,2,3,4,5].map((i) => (
                      <View key={i} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i <= score ? color : colors.borderSubtle }} />
                    ))}
                  </View>
                  <AppText variant="caption" style={{ color, fontSize: 11 }}>{label}</AppText>
                </View>
              );
            })()}
            <Input label="Confirme a senha" required value={form.password_confirm} onChangeText={(v) => setForm({ ...form, password_confirm: v })} secureTextEntry placeholder="Repita a senha" />

            {/* Família / Tester: show "I'm the responsible/parent" toggle */}
            {(planSlug === 'familia' || planSlug === 'tester') ? (
              <Checkbox
                value={form.isResponsible}
                onValueChange={(v) => setForm({ ...form, isResponsible: v })}
                label="Sou pai / responsável (não sou o jogador)"
                sublabel={
                  <AppText variant="caption" style={{ color: colors.textMuted, fontSize: 11 }}>
                    Marque se vai gerenciar o perfil de dependentes, como filho(a) ou atleta.
                  </AppText>
                }
              />
            ) : null}

            <View style={{ gap: 12, borderTopWidth: 1, borderTopColor: colors.borderSubtle, paddingTop: 12 }}>
              <Checkbox
                value={form.accept_terms}
                onValueChange={(v) => setForm({ ...form, accept_terms: v })}
                label="Aceito os Termos de Uso e Politica de Privacidade (LGPD) *"
                sublabel={
                  <Pressable onPress={() => Linking.openURL('https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm')}>
                    <AppText variant="caption" style={{ color: colors.accentNeon, textDecorationLine: 'underline' }}>
                      Ler Termos e Politica de Privacidade
                    </AppText>
                  </Pressable>
                }
              />
              <Checkbox
                value={form.marketing_consent}
                onValueChange={(v) => setForm({ ...form, marketing_consent: v })}
                label="Desejo receber novidades e comunicacoes por e-mail (opcional)"
              />
            </View>

            <Button title="Criar conta" onPress={onRegister} loading={submitting} />
            <Button title="Voltar" variant="ghost" onPress={() => setStep('plan')} />
          </>
        ) : null}

        {/* ── Step: OTP verification ────────────────────────────────────────── */}
        {step === 'otp' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="mail-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Verificacao de e-mail</AppText>
            </View>
            <AppText variant="muted">
              Enviamos um codigo de 6 digitos para <AppText variant="muted" style={{ fontWeight: '700' }}>{form.email}</AppText>. Digite-o abaixo.
            </AppText>
            <Input label="Codigo de verificacao" value={emailCode} onChangeText={setEmailCode} keyboardType="number-pad" placeholder="000000" />
            <Button title="Confirmar e-mail" onPress={onVerify} loading={submitting} />
            <Button title="Reenviar codigo" variant="secondary" onPress={resendOtp} loading={resending} />
          </>
        ) : null}

        {/* ── Step: Payment (paid plans only) ──────────────────────────────── */}
        {step === 'payment' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Ionicons name="card-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>
                Ativar Plano {PLAN_FALLBACK[planSlug].label}
              </AppText>
            </View>

            {paymentLoading ? (
              <View style={{ paddingVertical: 24, alignItems: 'center', gap: 12 }}>
                <ActivityIndicator size="large" color={colors.accentNeon} />
                <AppText variant="muted">Gerando cobrança PIX...</AppText>
              </View>
            ) : pixCode ? (
              <>
                <AppText variant="muted" style={{ marginBottom: 12 }}>
                  Escaneie o QR Code ou copie o código Pix abaixo para pagar {getPlanPrice(planSlug)}.
                </AppText>

                {/* PIX code display */}
                <View style={{ backgroundColor: colors.bgCard, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: colors.borderSubtle }}>
                  <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 6 }}>Pix copia e cola:</AppText>
                  <AppText variant="caption" numberOfLines={2} style={{ fontFamily: 'Poppins_400Regular', fontSize: 11, color: colors.textPrimary }}>
                    {pixCode}
                  </AppText>
                  <Pressable
                    onPress={copyPixCode}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, backgroundColor: `${colors.accentNeon}18`, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: `${colors.accentNeon}33` }}
                  >
                    <Ionicons name={pixCopied ? 'checkmark-circle' : 'copy-outline'} size={16} color={colors.accentNeon} />
                    <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>
                      {pixCopied ? 'Copiado!' : 'Copiar código'}
                    </AppText>
                  </Pressable>
                </View>

                <View style={{ backgroundColor: `${colors.accentNeon}08`, borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: `${colors.accentNeon}22` }}>
                  <AppText variant="caption" style={{ color: colors.textMuted, fontSize: 11 }}>
                    Após o pagamento, o plano será ativado automaticamente. Clique em "Já paguei" para continuar.
                  </AppText>
                </View>

                <Button title="Já paguei — continuar" onPress={proceedAfterPayment} />
                <Button
                  title="Pagar depois"
                  variant="ghost"
                  onPress={() => {
                    if (registeredUser) setUser(registeredUser);
                  }}
                />
              </>
            ) : (
              <>
                <AppText variant="muted" style={{ marginBottom: 16 }}>
                  Não foi possível gerar a cobrança agora. Complete o pagamento em "Minha assinatura" após entrar no app.
                </AppText>
                <Button title="Entrar no app" onPress={() => { if (registeredUser) setUser(registeredUser); }} />
              </>
            )}
          </>
        ) : null}

        {/* ── Step: Profile setup ───────────────────────────────────────────── */}
        {step === 'profile' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="person-add-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Perfil esportivo</AppText>
            </View>
            <AppText variant="muted">Preencha seus dados para encontrar torneios compativeis. Pode pular e configurar depois.</AppText>

            <Input label="Nome de exibicao" value={profile.display_name} onChangeText={(v) => setProfile({ ...profile, display_name: v })} autoCapitalize="words" />
            <Input label="Ano de nascimento" value={profile.birth_year} onChangeText={(v) => setProfile({ ...profile, birth_year: v.replace(/\D/g, '').slice(0, 4) })} keyboardType="number-pad" placeholder="Ex: 2008" />
            <SelectField label="Genero" value={profile.gender} options={GENDER_OPTIONS} onSelect={(v) => setProfile({ ...profile, gender: v })} placeholder="Selecione" />
            <SelectField label="Estado (UF)" value={profile.home_state} options={UF_OPTIONS} onSelect={(v) => setProfile({ ...profile, home_state: v, home_city: '' })} />
            <SelectField label="Cidade" value={profile.home_city} options={cities} onSelect={(v) => setProfile({ ...profile, home_city: v })} placeholder={loadingCities ? 'Carregando...' : 'Selecione a cidade'} loading={loadingCities} searchable />
            <FederationSelect value={profile.federation} onChange={(id) => setProfile({ ...profile, federation: id })} />
            <SelectField label="Modalidade principal" value={profile.modality} options={MOBILE_MODALITY_OPTIONS} onSelect={(v) => setProfile({ ...profile, modality: v })} placeholder="Selecione a modalidade" />
            <SelectField label="Nivel competitivo" value={profile.competitive_level} options={LEVEL_OPTIONS} onSelect={(v) => setProfile({ ...profile, competitive_level: v })} />
            <SelectField label="Classe (FPT/CBT)" value={profile.tennis_class} options={CLASS_OPTIONS} onSelect={(v) => setProfile({ ...profile, tennis_class: v })} placeholder="Opcional" />

            <Button title="Finalizar cadastro" onPress={onFinish} loading={submitting} />
            <Button title="Pular (configurar depois)" variant="ghost" onPress={() => { if (registeredUser) setUser(registeredUser); }} />
          </>
        ) : null}

        {/* ── Step: UTR profile linking ─────────────────────────────────── */}
        {step === 'utr' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Ionicons name="tennisball-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Seu perfil na UTR</AppText>
            </View>
            <AppText variant="muted" style={{ marginBottom: 16 }}>
              Encontramos estes possíveis perfis na UTR. Algum deles é você?
            </AppText>

            {utrSearching ? (
              <View style={{ paddingVertical: 24, alignItems: 'center', gap: 10 }}>
                <ActivityIndicator color={colors.accentNeon} />
                <AppText variant="muted" style={{ fontSize: 12 }}>Buscando seu perfil UTR...</AppText>
              </View>
            ) : utrCandidates.length === 0 ? (
              <View style={{ paddingVertical: 16, alignItems: 'center', gap: 6 }}>
                <Ionicons name="search-outline" size={32} color={colors.textMuted} />
                <AppText variant="muted" style={{ textAlign: 'center', fontSize: 13 }}>
                  Não encontramos perfis UTR para este nome.{'\n'}Você poderá vincular depois no seu perfil.
                </AppText>
              </View>
            ) : (
              <>
                {utrCandidates.map((c) => (
                  <View
                    key={c.utr_player_id}
                    style={{
                      backgroundColor: colors.bgCard,
                      borderRadius: 14, borderWidth: 1, borderColor: colors.borderSubtle,
                      padding: 14, marginBottom: 10,
                    }}
                  >
                    <AppText style={{ fontWeight: '700', fontSize: 15, color: colors.textPrimary, marginBottom: 2 }}>
                      {c.display_name}
                    </AppText>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                      {c.country ? <AppText variant="muted" style={{ fontSize: 11 }}>{c.country}</AppText> : null}
                      {c.location ? <AppText variant="muted" style={{ fontSize: 11 }}>· {c.location}</AppText> : null}
                    </View>
                    {(c.singles_utr || c.doubles_utr) ? (
                      <View style={{ flexDirection: 'row', gap: 20, marginBottom: 12 }}>
                        <View style={{ alignItems: 'center' }}>
                          <AppText style={{ fontSize: 22, fontWeight: '900', color: colors.textPrimary }}>{c.singles_utr}</AppText>
                          <AppText variant="muted" style={{ fontSize: 10 }}>UTR Simples</AppText>
                        </View>
                        <View style={{ alignItems: 'center' }}>
                          <AppText style={{ fontSize: 22, fontWeight: '900', color: colors.textPrimary }}>{c.doubles_utr}</AppText>
                          <AppText variant="muted" style={{ fontSize: 10 }}>UTR Duplas</AppText>
                        </View>
                      </View>
                    ) : (
                      <AppText variant="muted" style={{ fontSize: 11, fontStyle: 'italic', marginBottom: 12 }}>
                        Rating extraído automaticamente após confirmar.
                      </AppText>
                    )}
                    <Button
                      title={utrLinking ? 'Salvando...' : 'Este sou eu'}
                      variant="secondary"
                      onPress={() => _onSelectUtrCandidate(c)}
                    />
                  </View>
                ))}
              </>
            )}

            <Button
              title="Não sou nenhum desses"
              variant="ghost"
              onPress={_finishAfterUtr}
            />
          </>
        ) : null}

        {/* ── Step: Parent done (tester responsible — no profile needed) ──── */}
        {step === 'done_parent' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="shield-checkmark-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Conta criada!</AppText>
            </View>
            <AppText variant="muted">
              Sua conta de responsável foi criada com sucesso.
            </AppText>
            <View style={{ backgroundColor: `${colors.accentBlue}12`, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: `${colors.accentBlue}30`, gap: 6 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="information-circle-outline" size={16} color={colors.accentBlue} />
                <AppText variant="body" style={{ fontWeight: '700', color: colors.accentBlue, fontSize: 13 }}>Como adicionar dependentes</AppText>
              </View>
              <AppText variant="muted" style={{ fontSize: 12, lineHeight: 19 }}>
                1. Acesse a aba <AppText style={{ fontWeight: '700', color: colors.textSecondary }}>Perfil</AppText>{'\n'}
                2. Na seção <AppText style={{ fontWeight: '700', color: colors.textSecondary }}>Perfis esportivos</AppText>, toque em <AppText style={{ fontWeight: '700', color: colors.textSecondary }}>Adicionar perfil</AppText>{'\n'}
                3. Preencha os dados do seu filho ou dependente
              </AppText>
            </View>
            <Button title="Entrar no app" onPress={() => { if (registeredUser) setUser(registeredUser); }} />
          </>
        ) : null}

        {/* ── Step: Dependent creation (Família responsible only) ────────── */}
        {step === 'dependent' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="people-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Cadastrar dependente</AppText>
            </View>
            <AppText variant="muted">
              Crie a conta do seu dependente. Depois ele podera entrar com este e-mail e senha para preencher seu perfil esportivo.
            </AppText>

            <Input label="Nome completo do dependente" required value={dependentForm.full_name} onChangeText={(v) => setDependentForm({ ...dependentForm, full_name: v })} autoCapitalize="words" placeholder="Ex: Pedro Silva" />
            <Input label="E-mail do dependente" required value={dependentForm.email} onChangeText={(v) => setDependentForm({ ...dependentForm, email: v.trim() })} autoCapitalize="none" keyboardType="email-address" placeholder="dependente@email.com" />
            <Input label="Celular do dependente" value={dependentForm.phone} onChangeText={(v) => setDependentForm({ ...dependentForm, phone: v.replace(/\D/g, '') })} keyboardType="phone-pad" placeholder="Opcional" />
            <Input label="Senha do dependente" required value={dependentForm.password} onChangeText={(v) => setDependentForm({ ...dependentForm, password: v })} secureTextEntry placeholder="Minimo 8 caracteres" />
            <Input label="Confirme a senha" required value={dependentForm.password_confirm} onChangeText={(v) => setDependentForm({ ...dependentForm, password_confirm: v })} secureTextEntry placeholder="Repita a senha" />

            <Button title="Cadastrar dependente" onPress={onCreateDependent} loading={submitting} />
            <Button title="Pular por enquanto" variant="ghost" onPress={() => { if (registeredUser) setUser(registeredUser); }} />
          </>
        ) : null}
      </Card>

      {(step === 'plan' || step === 'form') ? (
        <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 4 }}>
          <AppText variant="body" style={{ color: colors.textSecondary }}>Ja possui conta?</AppText>
          <Pressable onPress={() => navigation.navigate('Login')}>
            <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '600' }}>Entrar</AppText>
          </Pressable>
        </View>
      ) : null}
    </Screen>
  );
}
