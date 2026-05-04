import React, { useEffect, useState } from 'react';
import { Alert, Image, Pressable, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import Toast from 'react-native-toast-message';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { deleteAccount, uploadAvatar } from '../../services/auth';
import { deleteProfile, listChildren, listProfiles, requestDataExport, setPrimary, updateProfile } from '../../services/data';
import { extractApiError, mediaUrl } from '../../services/api';
import { ParentChild, PlayerProfile } from '../../types';
import { GENDER_LABELS, LEVEL_LABELS, ROLE_LABELS, TENNIS_CLASS_LABELS } from '../../utils/format';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader, SelectField } from '../../components/ui';

type Props = BottomTabScreenProps<MainTabParamList, 'Profile'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;

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

const GENDER_OPTIONS = [{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }];
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

export function ProfileScreen(_: Props) {
  const { colors, theme, toggle } = useTheme();
  const { user, setUser, logout } = useAuth();
  const navigation = useNavigation<StackNav>();
  const [loading, setLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [editing, setEditing] = useState<PlayerProfile | null>(null);
  const [children, setChildren] = useState<ParentChild[]>([]);

  const isParent = user?.role === 'parent';
  const isManagedChild = !!user?.managed_by_parent;

  async function load() {
    setLoading(true);
    setProfileError(null);
    try {
      setProfiles(await listProfiles() as PlayerProfile[]);
      if (isParent) {
        try { setChildren(await listChildren() as ParentChild[]); } catch { /* ignore */ }
      }
    }
    catch { setProfileError('Não foi possível carregar seus perfis. Verifique sua conexão.'); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleAvatarChange() {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.8, allowsEditing: true, aspect: [1, 1] });
    if (result.canceled || !result.assets[0]) return;
    try {
      const updated = await uploadAvatar(result.assets[0]);
      setUser(updated);
      Toast.show({ type: 'success', text1: 'Foto atualizada!' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao enviar foto', text2: extractApiError(err) });
    }
  }

  async function makePrimaryProfile(id: number) {
    try { await setPrimary(id); await load(); Toast.show({ type: 'success', text1: 'Perfil principal atualizado.' }); }
    catch { Toast.show({ type: 'error', text1: 'Não foi possível definir o perfil principal.' }); }
  }

  function removeProfile(id: number) {
    Alert.alert(
      'Remover perfil',
      'Tem certeza que deseja remover este perfil esportivo?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover',
          style: 'destructive',
          onPress: async () => {
            try { await deleteProfile(id); await load(); Toast.show({ type: 'success', text1: 'Perfil removido.' }); }
            catch (err) { Toast.show({ type: 'error', text1: 'Erro ao remover perfil', text2: extractApiError(err) }); }
          },
        },
      ],
    );
  }

  function handleDeleteAccount() {
    Alert.alert(
      'Excluir conta',
      'Esta ação é irreversível. Todos os seus dados serão permanentemente removidos. Deseja continuar?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Excluir conta',
          style: 'destructive',
          onPress: async () => {
            try { await deleteAccount(); setUser(null); }
            catch (err) { Toast.show({ type: 'error', text1: 'Erro ao excluir conta', text2: extractApiError(err) }); }
          },
        },
      ],
    );
  }

  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role ?? ''] ?? user?.role ?? '';

  return (
    <Screen>
      {/* User header */}
      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
          <Pressable onPress={handleAvatarChange} style={{ position: 'relative' }}>
            <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: `${colors.accentNeon}22`, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: `${colors.accentNeon}44` }}>
              {user?.avatar
                ? <Image source={{ uri: mediaUrl(user.avatar) }} style={{ width: '100%', height: '100%' }} />
                : <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 26 }}>{avatarLetter}</AppText>}
            </View>
            <View style={{ position: 'absolute', bottom: 0, right: 0, width: 24, height: 24, borderRadius: 12, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: colors.bgBase }}>
              <Ionicons name="camera" size={12} color={colors.bgBase} />
            </View>
          </Pressable>
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontWeight: '700', fontSize: 17 }}>{user?.full_name || '—'}</AppText>
            <AppText variant="caption" style={{ marginTop: 2 }}>{user?.email}</AppText>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <View style={{ backgroundColor: `${colors.accentBlue}22`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>{roleLabel}</AppText>
              </View>
              {user?.is_staff ? (
                <View style={{ backgroundColor: `${colors.accentNeon}22`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                  <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '600' }}>Staff</AppText>
                </View>
              ) : null}
            </View>
          </View>
        </View>
      </Card>

      {/* Parent info for child accounts */}
      {isManagedChild && user?.parent_info ? (
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Ionicons name="shield-outline" size={18} color={colors.accentBlue} />
            <AppText variant="body" style={{ fontWeight: '700' }}>Meu responsável</AppText>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.accentBlue}22`, alignItems: 'center', justifyContent: 'center' }}>
              <AppText variant="body" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 16 }}>
                {(user.parent_info.full_name || 'R').slice(0, 1).toUpperCase()}
              </AppText>
            </View>
            <View>
              <AppText variant="body" style={{ fontWeight: '600' }}>{user.parent_info.full_name || '—'}</AppText>
              <AppText variant="caption">{user.parent_info.email}</AppText>
            </View>
          </View>
        </Card>
      ) : null}

      {/* Account actions */}
      <Card>
        <AppText variant="body" style={{ fontWeight: '700', marginBottom: 4 }}>Configurações da conta</AppText>
        <Pressable
          onPress={toggle}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
        >
          <Ionicons name={theme === 'dark' ? 'sunny-outline' : 'moon-outline'} size={18} color={colors.textSecondary} />
          <AppText variant="body">{theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'}</AppText>
        </Pressable>
        {!isManagedChild ? (
          <Pressable
            onPress={() => navigation.navigate('Subscription')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
          >
            <Ionicons name="card-outline" size={18} color={colors.textSecondary} />
            <AppText variant="body">Minha assinatura</AppText>
            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ marginLeft: 'auto' }} />
          </Pressable>
        ) : null}
        <Pressable
          onPress={() => navigation.navigate('MyRegistrations')}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
        >
          <Ionicons name="ticket-outline" size={18} color={colors.textSecondary} />
          <AppText variant="body">Inscrições</AppText>
          <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ marginLeft: 'auto' }} />
        </Pressable>
        {user?.role === 'coach' ? (
          <Pressable
            onPress={() => navigation.navigate('Coach')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
          >
            <Ionicons name="people-outline" size={18} color={colors.textSecondary} />
            <AppText variant="body">Meus alunos</AppText>
            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ marginLeft: 'auto' }} />
          </Pressable>
        ) : null}
        {user?.is_staff ? (
          <Pressable
            onPress={() => navigation.navigate('AdminPanel')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
          >
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.textSecondary} />
            <AppText variant="body">Painel administrativo</AppText>
            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ marginLeft: 'auto' }} />
          </Pressable>
        ) : null}
        <Pressable
          onPress={() => navigation.navigate('Tabs', { screen: 'Alerts' } as never)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
        >
          <Ionicons name="notifications-outline" size={18} color={colors.textSecondary} />
          <AppText variant="body">Notificações e alertas</AppText>
          <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ marginLeft: 'auto' }} />
        </Pressable>
        <Pressable
          onPress={logout}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 }}
        >
          <Ionicons name="log-out-outline" size={18} color={colors.danger} />
          <AppText variant="body" style={{ color: colors.danger }}>Sair da conta</AppText>
        </Pressable>
      </Card>

      {/* Children section for parents */}
      {isParent && children.length > 0 ? (
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Ionicons name="people-outline" size={18} color={colors.accentNeon} />
            <AppText variant="body" style={{ fontWeight: '700' }}>Meus filhos</AppText>
          </View>
          {children.map((link) => (
            <View key={link.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
              <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.accentBlue}22`, alignItems: 'center', justifyContent: 'center' }}>
                <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 14 }}>
                  {(link.child_detail?.full_name || 'F').slice(0, 1).toUpperCase()}
                </AppText>
              </View>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontWeight: '600' }}>{link.child_detail?.full_name || '—'}</AppText>
                <AppText variant="caption">{link.child_detail?.email}</AppText>
              </View>
            </View>
          ))}
        </Card>
      ) : null}

      {/* Sports profiles */}
      <View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <View>
            <AppText variant="section">Perfis esportivos</AppText>
            <AppText variant="caption" style={{ marginTop: 2 }}>{isParent ? 'Perfis esportivos dos seus filhos' : 'Gerencie seus perfis de jogador'}</AppText>
          </View>
          {!isParent ? (
            <Pressable
              onPress={() => navigation.navigate('Onboarding')}
              style={{ backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}55`, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center' }}
            >
              <Ionicons name="add" size={16} color={colors.accentNeon} />
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Novo</AppText>
            </Pressable>
          ) : null}
        </View>

        {loading ? <LoadingBlock /> : profileError ? (
          <EmptyState
            icon="alert-circle-outline"
            title="Erro ao carregar perfis"
            subtitle={profileError}
            action={<Button title="Tentar novamente" onPress={load} />}
          />
        ) : profiles.length === 0 ? (
          <EmptyState
            title={isParent ? 'Nenhum perfil esportivo dos filhos encontrado.' : 'Nenhum perfil criado.'}
            subtitle={isParent ? 'Peça ao seu filho para completar o perfil esportivo no app.' : 'Crie um perfil para ver torneios compatíveis, agenda e resultados.'}
          />
        ) : profiles.map((p) =>
          editing?.id === p.id ? (
            <ProfileEditor
              key={p.id}
              profile={p}
              onSaved={async () => { setEditing(null); await load(); }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <ProfileCard
              key={p.id}
              profile={p}
              colors={colors}
              onEdit={() => setEditing(p)}
              onMakePrimary={() => makePrimaryProfile(p.id)}
              onRemove={() => removeProfile(p.id)}
            />
          )
        )}
      </View>

      {/* Privacy */}
      <PrivacyCard onDeleteAccount={handleDeleteAccount} />
    </Screen>
  );
}

function PrivacyCard({ onDeleteAccount }: { onDeleteAccount: () => void }) {
  const { colors } = useTheme();
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      await requestDataExport();
      Toast.show({ type: 'success', text1: 'Dados exportados!', text2: 'O arquivo JSON foi baixado.' });
    } catch {
      Toast.show({ type: 'error', text1: 'Não foi possível exportar os dados.' });
    } finally {
      setExporting(false);
    }
  }

  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <Ionicons name="shield-outline" size={18} color={colors.textMuted} />
        <AppText variant="body" style={{ fontWeight: '700' }}>Privacidade e dados (LGPD)</AppText>
      </View>
      <AppText variant="muted" style={{ marginBottom: 12 }}>
        Conforme a LGPD, você pode exportar ou excluir todos os seus dados a qualquer momento.
      </AppText>
      <Button
        title={exporting ? 'Exportando...' : 'Exportar meus dados'}
        variant="secondary"
        onPress={handleExport}
        loading={exporting}
        style={{ marginBottom: 8 }}
      />
      <Button title="Excluir minha conta" variant="danger" onPress={onDeleteAccount} />
    </Card>
  );
}

function ProfileCard({ profile: p, colors, onEdit, onMakePrimary, onRemove }: {
  profile: PlayerProfile;
  colors: any;
  onEdit: () => void;
  onMakePrimary: () => void;
  onRemove: () => void;
}) {
  const classLabel = p.tennis_class ? (TENNIS_CLASS_LABELS[p.tennis_class] ?? `Classe ${p.tennis_class}`) : null;
  const levelLabel = LEVEL_LABELS[p.competitive_level] ?? p.competitive_level;
  const genderLabel = p.gender ? (GENDER_LABELS[p.gender] ?? p.gender) : null;

  return (
    <Card style={{ marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <AppText variant="body" style={{ fontWeight: '700', fontSize: 16, flex: 1 }}>{p.display_name}</AppText>
        {p.is_primary ? (
          <View style={{ backgroundColor: `${colors.accentNeon}22`, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 }}>
            <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Principal</AppText>
          </View>
        ) : null}
      </View>

      <View style={{ gap: 4 }}>
        {(p.birth_year || p.sporting_age) ? (
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">
              {p.birth_year ? `Nascimento: ${p.birth_year}` : ''}{p.sporting_age ? ` • ${p.sporting_age} anos esportivos` : ''}
            </AppText>
          </View>
        ) : null}
        {genderLabel ? (
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="person-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">{genderLabel}</AppText>
          </View>
        ) : null}
        {(p.home_city || p.home_state) ? (
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="location-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">{[p.home_city, p.home_state].filter(Boolean).join('/')} • raio {p.travel_radius_km} km</AppText>
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
          <Ionicons name="trophy-outline" size={13} color={colors.textMuted} />
          <AppText variant="caption">{levelLabel}{classLabel ? ` • ${classLabel}` : ''}</AppText>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
        <Button title="Editar" variant="secondary" onPress={onEdit} style={{ flex: 1 }} />
        {!p.is_primary ? <Button title="Tornar principal" variant="ghost" onPress={onMakePrimary} style={{ flex: 1 }} /> : null}
        <Button title="Remover" variant="danger" onPress={onRemove} style={{ flex: p.is_primary ? 2 : 1 }} />
      </View>
    </Card>
  );
}

function ProfileEditor({ profile, onSaved, onCancel }: { profile: PlayerProfile; onSaved: () => Promise<void>; onCancel: () => void; }) {
  const [form, setForm] = useState({
    display_name: profile.display_name,
    birth_year: profile.birth_year ? String(profile.birth_year) : '',
    gender: profile.gender ?? '',
    home_state: profile.home_state ?? 'SP',
    home_city: profile.home_city ?? '',
    travel_radius_km: String(profile.travel_radius_km ?? 100),
    tennis_class: profile.tennis_class ?? '',
    competitive_level: profile.competitive_level ?? 'amateur',
  });
  const [saving, setSaving] = useState(false);
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  useEffect(() => { loadCities(form.home_state); }, [form.home_state]);

  async function loadCities(uf: string) {
    if (!uf) return;
    setLoadingCities(true);
    try {
      const res = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/estados/${uf}/municipios`);
      const data: any[] = await res.json();
      setCities(data.map((c) => ({ value: c.nome, label: c.nome })).sort((a, b) => a.label.localeCompare(b.label, 'pt-BR')));
    } catch {
      setCities([]);
    } finally {
      setLoadingCities(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      await updateProfile(profile.id, {
        ...form,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        travel_radius_km: Number(form.travel_radius_km) || 100,
      } as any);
      Toast.show({ type: 'success', text1: 'Perfil atualizado' });
      await onSaved();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao salvar', text2: extractApiError(err) });
    } finally { setSaving(false); }
  }

  return (
    <Card style={{ marginBottom: 10 }}>
      <AppText variant="body" style={{ fontWeight: '700' }}>Editando: {profile.display_name}</AppText>
      <Input label="Nome de exibição" value={form.display_name} onChangeText={(v) => setForm({ ...form, display_name: v })} />
      <Input
        label="Ano de nascimento"
        value={form.birth_year}
        onChangeText={(v) => setForm({ ...form, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
        keyboardType="number-pad"
        placeholder="Ex: 1990"
      />
      <SelectField label="Gênero" value={form.gender} options={GENDER_OPTIONS} onSelect={(v) => setForm({ ...form, gender: v as 'M' | 'F' | '' })} />
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
        placeholder={loadingCities ? 'Carregando...' : 'Selecione a cidade'}
        loading={loadingCities}
        searchable
      />
      <SelectField
        label="Raio de viagem"
        value={form.travel_radius_km}
        options={RADIUS_OPTIONS}
        onSelect={(v) => setForm({ ...form, travel_radius_km: v })}
      />
      <SelectField label="Nível competitivo" value={form.competitive_level} options={LEVEL_OPTIONS} onSelect={(v) => setForm({ ...form, competitive_level: v as PlayerProfile['competitive_level'] })} />
      <SelectField label="Classe" value={form.tennis_class} options={CLASS_OPTIONS} onSelect={(v) => setForm({ ...form, tennis_class: v })} />
      <Button title="Salvar alterações" onPress={save} loading={saving} />
      <Button title="Cancelar" variant="ghost" onPress={onCancel} />
    </Card>
  );
}
