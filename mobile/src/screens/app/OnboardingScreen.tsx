import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { createProfile, linkUtr, searchUtr } from '../../services/data';
import { extractApiError } from '../../services/api';
import { UtrCandidate } from '../../types';
import { LEVEL_LABELS, TENNIS_CLASS_LABELS } from '../../utils/format';
import { AppText, Button, Card, Input, MultiSelectField, Screen, SectionHeader, SelectField } from '../../components/ui';

type Props = NativeStackScreenProps<MainStackParamList, 'Onboarding'>;

const GENDER_OPTIONS = [
  { value: 'M', label: 'Masculino' },
  { value: 'F', label: 'Feminino' },
];

const UF_OPTIONS = [
  { value: 'AC', label: 'AC – Acre' },
  { value: 'AL', label: 'AL – Alagoas' },
  { value: 'AP', label: 'AP – Amapá' },
  { value: 'AM', label: 'AM – Amazonas' },
  { value: 'BA', label: 'BA – Bahia' },
  { value: 'CE', label: 'CE – Ceará' },
  { value: 'DF', label: 'DF – Distrito Federal' },
  { value: 'ES', label: 'ES – Espírito Santo' },
  { value: 'GO', label: 'GO – Goiás' },
  { value: 'MA', label: 'MA – Maranhão' },
  { value: 'MT', label: 'MT – Mato Grosso' },
  { value: 'MS', label: 'MS – Mato Grosso do Sul' },
  { value: 'MG', label: 'MG – Minas Gerais' },
  { value: 'PA', label: 'PA – Pará' },
  { value: 'PB', label: 'PB – Paraíba' },
  { value: 'PR', label: 'PR – Paraná' },
  { value: 'PE', label: 'PE – Pernambuco' },
  { value: 'PI', label: 'PI – Piauí' },
  { value: 'RJ', label: 'RJ – Rio de Janeiro' },
  { value: 'RN', label: 'RN – Rio Grande do Norte' },
  { value: 'RS', label: 'RS – Rio Grande do Sul' },
  { value: 'RO', label: 'RO – Rondônia' },
  { value: 'RR', label: 'RR – Roraima' },
  { value: 'SC', label: 'SC – Santa Catarina' },
  { value: 'SP', label: 'SP – São Paulo' },
  { value: 'SE', label: 'SE – Sergipe' },
  { value: 'TO', label: 'TO – Tocantins' },
];

const LEVEL_OPTIONS = Object.entries(LEVEL_LABELS).map(([value, label]) => ({ value, label }));
const CLASS_OPTIONS = [
  { value: '', label: 'Sem classe definida' },
  ...Object.entries(TENNIS_CLASS_LABELS).map(([value, label]) => ({ value, label })),
];

const ALL_STATES_OPTION = { value: '__ALL__', label: '🌎 Todo o Brasil (todos os estados)' };
const TRAVEL_STATE_OPTIONS = [
  ALL_STATES_OPTION,
  ...UF_OPTIONS,
];

export function OnboardingScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const [submitting, setSubmitting] = useState(false);
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);
  const [citiesError, setCitiesError] = useState(false);
  const ALL_BR_UFS = UF_OPTIONS.map((o) => o.value);

  // ── UTR step (shown after profile creation) ──────────────────────────────────
  const [utrStep, setUtrStep] = useState(false);
  const [utrSearching, setUtrSearching] = useState(false);
  const [utrCandidates, setUtrCandidates] = useState<UtrCandidate[]>([]);
  const [utrLinking, setUtrLinking] = useState(false);
  const [createdProfileId, setCreatedProfileId] = useState<number | null>(null);

  const [form, setForm] = useState({
    display_name: '',
    birth_year: '',
    gender: '',
    home_state: 'SP',
    home_city: '',
    travel_states: [] as string[],
    competitive_level: 'amateur',
    tennis_class: '',
  });

  function handleTravelStatesSelect(vals: string[]) {
    if (vals.includes('__ALL__')) {
      // Tapped "Todo o Brasil" — select all UFs
      setForm((f) => ({ ...f, travel_states: ALL_BR_UFS }));
    } else {
      setForm((f) => ({ ...f, travel_states: vals }));
    }
  }

  useEffect(() => {
    loadCities(form.home_state);
  }, [form.home_state]);

  async function loadCities(uf: string) {
    if (!uf) return;
    setLoadingCities(true);
    setCities([]);
    setCitiesError(false);
    try {
      const res = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/estados/${uf}/municipios`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: any[] = await res.json();
      setCities(data.map((c) => ({ value: c.nome, label: c.nome })).sort((a, b) => a.label.localeCompare(b.label, 'pt-BR')));
    } catch {
      setCitiesError(true);
      Toast.show({ type: 'error', text1: 'Erro ao carregar cidades', text2: 'Verifique sua conexão e tente novamente.' });
    } finally {
      setLoadingCities(false);
    }
  }

  async function finish() {
    if (!form.display_name.trim()) {
      Toast.show({ type: 'error', text1: 'Informe seu nome de exibição' });
      return;
    }
    setSubmitting(true);
    try {
      const created = await createProfile({
        display_name: form.display_name.trim(),
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        gender: (form.gender || undefined) as any,
        home_state: form.home_state,
        home_city: form.home_city,
        travel_states: form.travel_states,
        competitive_level: form.competitive_level as any,
        tennis_class: form.tennis_class || '',
        is_primary: true,
      } as any);

      if (created?.id) {
        setCreatedProfileId(created.id);
        setUtrStep(true);
        _searchUtrBackground(created.id, form.display_name.trim());
      } else {
        Toast.show({ type: 'success', text1: 'Perfil criado com sucesso!' });
        navigation.goBack();
      }
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar perfil', text2: extractApiError(err) });
    } finally {
      setSubmitting(false);
    }
  }

  async function _searchUtrBackground(profileId: number, name: string) {
    if (!name || name.length < 2) return;
    setUtrSearching(true);
    setUtrCandidates([]);
    try {
      const result = await searchUtr(profileId, name);
      setUtrCandidates((result.candidates ?? []).slice(0, 3));
    } catch {
      // Silently fail
    } finally {
      setUtrSearching(false);
    }
  }

  function _finishUtr() {
    Toast.show({ type: 'success', text1: 'Perfil criado com sucesso!' });
    navigation.goBack();
  }

  async function _selectUtrCandidate(candidate: UtrCandidate) {
    if (!createdProfileId || utrLinking) return;
    setUtrLinking(true);
    try {
      await linkUtr(createdProfileId, candidate);
    } catch {
      // Non-blocking
    } finally {
      setUtrLinking(false);
      _finishUtr();
    }
  }

  // ── UTR step screen ──────────────────────────────────────────────────────────
  if (utrStep) {
    return (
      <Screen>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Ionicons name="tennisball-outline" size={22} color={colors.accentNeon} />
          <SectionHeader title="Seu perfil na UTR" />
        </View>
        <AppText variant="muted" style={{ marginTop: -8, marginBottom: 16 }}>
          Encontramos estes possíveis perfis na UTR. Algum deles é você?
        </AppText>

        <Card>
          {utrSearching ? (
            <View style={{ paddingVertical: 24, alignItems: 'center', gap: 10 }}>
              <ActivityIndicator color={colors.accentNeon} />
              <AppText variant="muted" style={{ fontSize: 12 }}>Buscando seu perfil UTR...</AppText>
            </View>
          ) : utrCandidates.length === 0 ? (
            <View style={{ paddingVertical: 16, alignItems: 'center', gap: 8 }}>
              <Ionicons name="search-outline" size={36} color={colors.textMuted} />
              <AppText variant="muted" style={{ textAlign: 'center', fontSize: 13 }}>
                Não encontramos perfis UTR para este nome.{'\n'}Você poderá vincular depois em Configurações.
              </AppText>
            </View>
          ) : (
            <>
              {utrCandidates.map((c) => (
                <View
                  key={c.utr_player_id}
                  style={{
                    backgroundColor: colors.bgBase,
                    borderRadius: 12, borderWidth: 1, borderColor: colors.borderSubtle,
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
                    <View style={{ flexDirection: 'row', gap: 24, marginBottom: 12 }}>
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
                  {c.profile_url ? (
                    <AppText variant="muted" style={{ fontSize: 10, marginBottom: 10 }}>ID: {c.utr_player_id}</AppText>
                  ) : null}
                  <Button
                    title={utrLinking ? 'Salvando...' : 'Este sou eu'}
                    variant="secondary"
                    onPress={() => _selectUtrCandidate(c)}
                  />
                </View>
              ))}
            </>
          )}
        </Card>

        <Button
          title="Não sou nenhum desses"
          variant="ghost"
          onPress={_finishUtr}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="person-add-outline" size={22} color={colors.accentNeon} />
        <SectionHeader title="Novo perfil esportivo" />
      </View>
      <AppText variant="muted" style={{ marginTop: -8 }}>Preencha seus dados para encontrar torneios compatíveis com você.</AppText>

      <Card>
        <AppText variant="body" style={{ fontWeight: '700' }}>Dados pessoais</AppText>
        <Input
          label="Nome de exibição"
          value={form.display_name}
          onChangeText={(v) => setForm({ ...form, display_name: v })}
          placeholder="Ex: Bruno Santos"
          autoCapitalize="words"
        />
        <Input
          label="Ano de nascimento"
          value={form.birth_year}
          onChangeText={(v) => setForm({ ...form, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
          keyboardType="number-pad"
          placeholder="Ex: 1995"
        />
        <SelectField
          label="Gênero"
          value={form.gender}
          options={GENDER_OPTIONS}
          onSelect={(v) => setForm({ ...form, gender: v })}
          placeholder="Selecione o gênero"
        />
      </Card>

      <Card>
        <AppText variant="body" style={{ fontWeight: '700' }}>Localização</AppText>
        <SelectField
          label="Estado (UF)"
          value={form.home_state}
          options={UF_OPTIONS}
          onSelect={(v) => setForm({ ...form, home_state: v, home_city: '' })}
        />
        <SelectField
          label="Cidade"
          value={form.home_city}
          options={cities}
          onSelect={(v) => setForm({ ...form, home_city: v })}
          placeholder={
            loadingCities
              ? 'Carregando cidades...'
              : cities.length === 0
              ? 'Selecione o estado primeiro'
              : 'Selecione a cidade'
          }
          loading={loadingCities}
          searchable
        />
        {citiesError && !loadingCities && (
          <Pressable onPress={() => loadCities(form.home_state)} style={{ paddingVertical: 6 }}>
            <AppText variant="caption" style={{ color: colors.statusClosing }}>
              Erro ao carregar cidades. Toque aqui para tentar novamente.
            </AppText>
          </Pressable>
        )}
        <MultiSelectField
          label="Estados onde aceita jogar"
          values={form.travel_states}
          options={TRAVEL_STATE_OPTIONS}
          onSelect={handleTravelStatesSelect}
          placeholder="Selecione os estados..."
          searchable
        />
      </Card>

      <Card>
        <AppText variant="body" style={{ fontWeight: '700' }}>Nível de jogo</AppText>
        <SelectField
          label="Nível competitivo"
          value={form.competitive_level}
          options={LEVEL_OPTIONS}
          onSelect={(v) => setForm({ ...form, competitive_level: v })}
        />
        <SelectField
          label="Classe (FPT/CBT)"
          value={form.tennis_class}
          options={CLASS_OPTIONS}
          onSelect={(v) => setForm({ ...form, tennis_class: v })}
          placeholder="Selecione a classe (opcional)"
        />
      </Card>

      <Button title="Criar perfil" onPress={finish} loading={submitting} />
      <Button title="Cancelar" variant="ghost" onPress={() => navigation.goBack()} />
    </Screen>
  );
}
