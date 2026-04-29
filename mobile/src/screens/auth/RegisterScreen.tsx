import React, { useEffect, useState } from 'react';
import { Linking, Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { AuthStackParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { createProfile } from '../../services/data';
import { extractApiError } from '../../services/api';
import { register, sendEmailOtp, verifyEmailOtp } from '../../services/auth';
import { User } from '../../types';
import { LEVEL_LABELS, TENNIS_CLASS_LABELS } from '../../utils/format';
import { AppText, Button, Card, Checkbox, Input, Screen, SelectField } from '../../components/ui';

function passwordStrength(pwd: string): { score: number; label: string; color: string } {
  if (!pwd) return { score: 0, label: '', color: 'transparent' };
  let score = 0;
  if (pwd.length >= 8)  score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  if (score <= 1) return { score, label: 'Fraca', color: '#ef4444' };
  if (score <= 2) return { score, label: 'Razoável', color: '#f59e0b' };
  if (score <= 3) return { score, label: 'Boa', color: '#3b82f6' };
  return { score, label: 'Forte', color: '#39ff14' };
}

type Props = NativeStackScreenProps<AuthStackParamList, 'Register'>;
type Step = 'form' | 'otp' | 'profile';

const GENDER_OPTIONS = [{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }];
const ROLE_OPTIONS = [
  { value: 'player', label: 'Jogador(a)' },
  { value: 'parent', label: 'Responsável / Pai ou Mãe' },
];
const UF_OPTIONS = [
  { value: 'AC', label: 'AC – Acre' }, { value: 'AL', label: 'AL – Alagoas' },
  { value: 'AP', label: 'AP – Amapá' }, { value: 'AM', label: 'AM – Amazonas' },
  { value: 'BA', label: 'BA – Bahia' }, { value: 'CE', label: 'CE – Ceará' },
  { value: 'DF', label: 'DF – Distrito Federal' }, { value: 'ES', label: 'ES – Espírito Santo' },
  { value: 'GO', label: 'GO – Goiás' }, { value: 'MA', label: 'MA – Maranhão' },
  { value: 'MT', label: 'MT – Mato Grosso' }, { value: 'MS', label: 'MS – Mato Grosso do Sul' },
  { value: 'MG', label: 'MG – Minas Gerais' }, { value: 'PA', label: 'PA – Pará' },
  { value: 'PB', label: 'PB – Paraíba' }, { value: 'PR', label: 'PR – Paraná' },
  { value: 'PE', label: 'PE – Pernambuco' }, { value: 'PI', label: 'PI – Piauí' },
  { value: 'RJ', label: 'RJ – Rio de Janeiro' }, { value: 'RN', label: 'RN – Rio Grande do Norte' },
  { value: 'RS', label: 'RS – Rio Grande do Sul' }, { value: 'RO', label: 'RO – Rondônia' },
  { value: 'RR', label: 'RR – Roraima' }, { value: 'SC', label: 'SC – Santa Catarina' },
  { value: 'SP', label: 'SP – São Paulo' }, { value: 'SE', label: 'SE – Sergipe' },
  { value: 'TO', label: 'TO – Tocantins' },
];
const LEVEL_OPTIONS = Object.entries(LEVEL_LABELS).map(([value, label]) => ({ value, label }));
const CLASS_OPTIONS = [
  { value: '', label: 'Sem classe definida' },
  ...Object.entries(TENNIS_CLASS_LABELS).map(([value, label]) => ({ value, label })),
];
const RADIUS_OPTIONS = [
  { value: '50', label: '50 km' }, { value: '100', label: '100 km' },
  { value: '200', label: '200 km' }, { value: '300', label: '300 km' },
  { value: '500', label: '500 km' }, { value: '1000', label: 'Todo o Brasil' },
];

export function RegisterScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const { setUser } = useAuth();
  const [step, setStep] = useState<Step>('form');
  const [registeredUser, setRegisteredUser] = useState<User | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
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
  const [emailCode, setEmailCode] = useState('');
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '',
    home_state: 'SP',
    home_city: '',
    travel_radius_km: '100',
    competitive_level: 'amateur',
    tennis_class: '',
  });
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  useEffect(() => { if (step === 'profile') loadCities(profile.home_state); }, [profile.home_state, step]);

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

  async function onRegister() {
    if (!form.full_name.trim()) return Toast.show({ type: 'error', text1: 'Informe seu nome completo' });
    if (!form.email.trim()) return Toast.show({ type: 'error', text1: 'Informe seu e-mail' });
    if (!form.phone.trim()) return Toast.show({ type: 'error', text1: 'Informe seu celular' });
    if (!form.password) return Toast.show({ type: 'error', text1: 'Defina uma senha' });
    if (form.password.length < 8) return Toast.show({ type: 'error', text1: 'A senha precisa ter no mínimo 8 caracteres' });
    if (form.password !== form.password_confirm) return Toast.show({ type: 'error', text1: 'As senhas não conferem' });
    if (!form.accept_terms) return Toast.show({ type: 'error', text1: 'Aceite os termos para continuar' });
    setSubmitting(true);
    try {
      const data = await register({ ...form });
      setRegisteredUser(data.user);
      setProfile((p) => ({ ...p, display_name: form.full_name }));
      setStep('otp');
      Toast.show({ type: 'success', text1: 'Conta criada! Verifique seu e-mail.' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar conta', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function onVerify() {
    setSubmitting(true);
    try {
      await verifyEmailOtp(emailCode.trim());
      setStep('profile');
      Toast.show({ type: 'success', text1: 'E-mail verificado!' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro na verificação', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function onFinish() {
    setSubmitting(true);
    try {
      await createProfile({
        display_name: profile.display_name || form.full_name || 'Jogador',
        birth_year: profile.birth_year ? Number(profile.birth_year) : null,
        gender: (profile.gender || undefined) as any,
        home_state: profile.home_state,
        home_city: profile.home_city,
        travel_radius_km: Number(profile.travel_radius_km) || 100,
        competitive_level: profile.competitive_level as any,
        tennis_class: profile.tennis_class || '',
        is_primary: true,
      } as any);
      if (registeredUser) setUser(registeredUser);
      Toast.show({ type: 'success', text1: 'Perfil criado! Bem-vindo!' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao finalizar cadastro', text2: extractApiError(err) });
    } finally { setSubmitting(false); }
  }

  async function resendOtp() {
    setResending(true);
    try { await sendEmailOtp(); Toast.show({ type: 'success', text1: 'Novo código enviado.' }); }
    catch { Toast.show({ type: 'error', text1: 'Não foi possível reenviar.' }); }
    finally { setResending(false); }
  }

  return (
    <Screen>
      <Card>
        <AppText variant="section">Criar conta</AppText>

        {/* ── Step 1: Form ─────────────────────────────────────────── */}
        {step === 'form' ? (
          <>
            <AppText variant="muted" style={{ marginBottom: 4 }}>
              Campos marcados com <AppText variant="muted" style={{ color: '#ef4444', fontWeight: '700' }}>*</AppText> são obrigatórios.
            </AppText>

            <Input label="Nome completo" required value={form.full_name} onChangeText={(v) => setForm({ ...form, full_name: v })} autoCapitalize="words" placeholder="Ex: Maria Silva" />
            <Input label="E-mail" required value={form.email} onChangeText={(v) => setForm({ ...form, email: v.trim() })} autoCapitalize="none" keyboardType="email-address" placeholder="seu@email.com" />
            <Input label="Celular" required value={form.phone} onChangeText={(v) => setForm({ ...form, phone: v.replace(/\D/g, '') })} keyboardType="phone-pad" placeholder="11999999999" />
            <Input label="Senha" required value={form.password} onChangeText={(v) => setForm({ ...form, password: v })} secureTextEntry placeholder="Mínimo 8 caracteres" />
            {form.password.length > 0 && (() => {
              const { score, label, color } = passwordStrength(form.password);
              return (
                <View style={{ marginTop: -8, marginBottom: 4, gap: 4 }}>
                  <View style={{ flexDirection: 'row', gap: 4 }}>
                    {[1,2,3,4,5].map((i) => (
                      <View key={i} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i <= score ? color : '#374151' }} />
                    ))}
                  </View>
                  <AppText variant="caption" style={{ color, fontSize: 11 }}>{label}</AppText>
                </View>
              );
            })()}
            <Input label="Confirme a senha" required value={form.password_confirm} onChangeText={(v) => setForm({ ...form, password_confirm: v })} secureTextEntry placeholder="Repita a senha" />

            <SelectField
              label="Tipo de conta"
              required
              value={form.role}
              options={ROLE_OPTIONS}
              onSelect={(v) => setForm({ ...form, role: v })}
            />

            <View style={{ gap: 12, borderTopWidth: 1, borderTopColor: colors.borderSubtle, paddingTop: 12 }}>
              <Checkbox
                value={form.accept_terms}
                onValueChange={(v) => setForm({ ...form, accept_terms: v })}
                label="Aceito os Termos de Uso e a Política de Privacidade (LGPD) *"
                sublabel={
                  <Pressable onPress={() => Linking.openURL('https://tournamenthub.app/termos')}>
                    <AppText variant="caption" style={{ color: colors.accentNeon, textDecorationLine: 'underline' }}>
                      Ler Termos e Política de Privacidade
                    </AppText>
                  </Pressable>
                }
              />
              <Checkbox
                value={form.marketing_consent}
                onValueChange={(v) => setForm({ ...form, marketing_consent: v })}
                label="Desejo receber novidades e comunicações por e-mail (opcional)"
              />
            </View>

            <Button title="Criar conta" onPress={onRegister} loading={submitting} />
          </>
        ) : null}

        {/* ── Step 2: OTP ──────────────────────────────────────────── */}
        {step === 'otp' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="mail-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Verificação de e-mail</AppText>
            </View>
            <AppText variant="muted">Enviamos um código de 6 dígitos para <AppText variant="muted" style={{ fontWeight: '700' }}>{form.email}</AppText>. Digite-o abaixo.</AppText>
            <Input label="Código de verificação" value={emailCode} onChangeText={setEmailCode} keyboardType="number-pad" placeholder="000000" />
            <Button title="Confirmar e-mail" onPress={onVerify} loading={submitting} />
            <Button title="Reenviar código" variant="secondary" onPress={resendOtp} loading={resending} />
          </>
        ) : null}

        {/* ── Step 3: Profile ──────────────────────────────────────── */}
        {step === 'profile' ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="person-add-outline" size={20} color={colors.accentNeon} />
              <AppText variant="body" style={{ fontWeight: '600' }}>Perfil esportivo</AppText>
            </View>
            <AppText variant="muted">Preencha seus dados para encontrar torneios compatíveis com você. Pode pular e configurar depois.</AppText>

            <Input label="Nome de exibição" value={profile.display_name} onChangeText={(v) => setProfile({ ...profile, display_name: v })} autoCapitalize="words" />
            <Input label="Ano de nascimento" value={profile.birth_year} onChangeText={(v) => setProfile({ ...profile, birth_year: v.replace(/\D/g, '').slice(0, 4) })} keyboardType="number-pad" placeholder="Ex: 2008" />
            <SelectField label="Gênero" value={profile.gender} options={GENDER_OPTIONS} onSelect={(v) => setProfile({ ...profile, gender: v })} placeholder="Selecione" />
            <SelectField label="Estado (UF)" value={profile.home_state} options={UF_OPTIONS} onSelect={(v) => setProfile({ ...profile, home_state: v, home_city: '' })} />
            <SelectField label="Cidade" value={profile.home_city} options={cities} onSelect={(v) => setProfile({ ...profile, home_city: v })} placeholder={loadingCities ? 'Carregando...' : 'Selecione a cidade'} loading={loadingCities} searchable />
            <SelectField label="Raio de viagem" value={profile.travel_radius_km} options={RADIUS_OPTIONS} onSelect={(v) => setProfile({ ...profile, travel_radius_km: v })} />
            <SelectField label="Nível competitivo" value={profile.competitive_level} options={LEVEL_OPTIONS} onSelect={(v) => setProfile({ ...profile, competitive_level: v })} />
            <SelectField label="Classe (FPT/CBT)" value={profile.tennis_class} options={CLASS_OPTIONS} onSelect={(v) => setProfile({ ...profile, tennis_class: v })} placeholder="Opcional" />

            <Button title="Finalizar cadastro" onPress={onFinish} loading={submitting} />
            <Button title="Pular (configurar depois)" variant="ghost" onPress={() => { if (registeredUser) setUser(registeredUser); }} />
          </>
        ) : null}
      </Card>

      {step === 'form' ? (
        <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 4 }}>
          <AppText variant="body" style={{ color: colors.textSecondary }}>Já possui conta?</AppText>
          <Pressable onPress={() => navigation.navigate('Login')}>
            <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '600' }}>Entrar</AppText>
          </Pressable>
        </View>
      ) : null}
    </Screen>
  );
}
