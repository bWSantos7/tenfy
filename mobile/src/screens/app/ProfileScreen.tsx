import React, { useEffect, useState } from 'react';
import { Alert, Image, Pressable, Share, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
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
import { createChildAccount } from '../../services/auth';
import {
  createChildProfile, deleteProfile, listChildren, listChildProfiles,
  listProfiles, requestDataExport, sendChildPasswordReset, setPrimary, updateProfile,
} from '../../services/data';
import { extractApiError, mediaUrl } from '../../services/api';
import { ParentChild, PlayerProfile } from '../../types';
import { GENDER_LABELS, LEVEL_LABELS, ROLE_LABELS, TENNIS_CLASS_LABELS } from '../../utils/format';
import { markProfileDirty } from '../../utils/profileRefresh';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader, SelectField, MultiSelectField } from '../../components/ui';

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
const ALL_UFS = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'];
const TRAVEL_STATE_OPTIONS = [
  { value: '__ALL__', label: 'Todo o Brasil (todos os estados)' },
  ...UF_OPTIONS,
];

type DependentData = { link: ParentChild; profiles: PlayerProfile[] };

export function ProfileScreen(_: Props) {
  const { colors, theme, toggle } = useTheme();
  const { user, setUser, logout } = useAuth();
  const navigation = useNavigation<StackNav>();
  const [loading, setLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Non-parent state
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [editing, setEditing] = useState<PlayerProfile | null>(null);

  // Parent state
  const [dependents, setDependents] = useState<DependentData[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingDep, setEditingDep] = useState<{ link: ParentChild; profile: PlayerProfile } | null>(null);
  const [creatingProfileFor, setCreatingProfileFor] = useState<ParentChild | null>(null);

  const isParent = user?.role === 'parent';
  const isManagedChild = !!user?.managed_by_parent;

  async function load() {
    setLoading(true);
    setProfileError(null);
    try {
      if (isParent) {
        const childLinks = await listChildren() as ParentChild[];
        const withProfiles = await Promise.all(
          childLinks.map(async (link) => {
            const profs = await listChildProfiles(link.child).catch(() => [] as PlayerProfile[]);
            return { link, profiles: profs };
          }),
        );
        setDependents(withProfiles);
      } else {
        setProfiles(await listProfiles() as PlayerProfile[]);
      }
    } catch {
      setProfileError('Não foi possível carregar seus perfis. Verifique sua conexão.');
    } finally {
      setLoading(false);
    }
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
            try {
              await deleteAccount();
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Erro ao excluir conta', text2: extractApiError(err) });
            } finally {
              setUser(null);
            }
          },
        },
      ],
    );
  }

  async function handleResetChildPassword(link: ParentChild) {
    Alert.alert(
      'Redefinir senha',
      `Enviar e-mail de redefinição de senha para ${link.child_detail.email}?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Enviar',
          onPress: async () => {
            try {
              await sendChildPasswordReset(link.id);
              Toast.show({ type: 'success', text1: 'E-mail enviado!', text2: `Instruções enviadas para ${link.child_detail.email}.` });
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Erro', text2: extractApiError(err) });
            }
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

      {/* ── Parents: unified dependents + sports profiles ── */}
      {isParent ? (
        <View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <View style={{ flex: 1 }}>
              <AppText variant="section">Meus dependentes - Perfil esportivo</AppText>
              <AppText variant="caption" style={{ marginTop: 2 }}>
                Gerencie os dependentes e seus perfis de jogador
              </AppText>
            </View>
            <Pressable
              onPress={() => { setShowAddForm(true); setEditingDep(null); setCreatingProfileFor(null); }}
              style={{ backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}55`, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center', marginLeft: 8 }}
            >
              <Ionicons name="add" size={16} color={colors.accentNeon} />
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Novo</AppText>
            </Pressable>
          </View>

          {showAddForm ? (
            <AddDependentForm
              onSuccess={async () => { setShowAddForm(false); await load(); }}
              onCancel={() => setShowAddForm(false)}
            />
          ) : null}

          {loading ? <LoadingBlock /> : profileError ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Erro ao carregar"
              subtitle={profileError}
              action={<Button title="Tentar novamente" onPress={load} />}
            />
          ) : dependents.length === 0 && !showAddForm ? (
            <EmptyState
              title="Nenhum dependente cadastrado"
              subtitle="Toque em Novo para adicionar um dependente e criar o perfil esportivo dele."
            />
          ) : dependents.map(({ link, profiles: childProfs }) => {
            const profile = childProfs[0] ?? null;
            if (editingDep?.link.id === link.id && editingDep.profile.id === profile?.id) {
              return (
                <ProfileEditor
                  key={link.id}
                  profile={editingDep.profile}
                  onSaved={async () => { setEditingDep(null); await load(); }}
                  onCancel={() => setEditingDep(null)}
                  restrictedMode={false}
                />
              );
            }
            if (creatingProfileFor?.id === link.id) {
              return (
                <CreateChildProfileForm
                  key={link.id}
                  link={link}
                  onSuccess={async () => { setCreatingProfileFor(null); await load(); }}
                  onCancel={() => setCreatingProfileFor(null)}
                />
              );
            }
            return (
              <DependentCard
                key={link.id}
                link={link}
                profile={profile}
                colors={colors}
                onEditProfile={() => profile && setEditingDep({ link, profile })}
                onCreateProfile={() => setCreatingProfileFor(link)}
                onResetPassword={() => handleResetChildPassword(link)}
              />
            );
          })}
        </View>
      ) : (
        /* ── Non-parents: own sports profiles ── */
        <View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <View style={{ flex: 1 }}>
              <AppText variant="section">Perfil esportivo</AppText>
              <AppText variant="caption" style={{ marginTop: 2 }}>
                {isManagedChild ? 'Seu perfil esportivo' : 'Gerencie seu perfil de jogador'}
              </AppText>
            </View>
            {!isManagedChild ? (
              <Pressable
                onPress={() => navigation.navigate('Onboarding')}
                style={{ backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}55`, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center', marginLeft: 8 }}
              >
                <Ionicons name="add" size={16} color={colors.accentNeon} />
                <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>
                  {profiles.length === 0 ? 'Criar' : 'Novo'}
                </AppText>
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
              title={isManagedChild ? 'Seu perfil esportivo ainda não foi preenchido.' : 'Nenhum perfil criado.'}
              subtitle={isManagedChild ? 'Peça ao seu responsável para ajudar a completar seu perfil.' : 'Crie um perfil para ver torneios compatíveis.'}
            />
          ) : profiles.map((p) =>
            editing?.id === p.id ? (
              <ProfileEditor
                key={p.id}
                profile={p}
                onSaved={async () => { setEditing(null); await load(); }}
                onCancel={() => setEditing(null)}
                restrictedMode={isManagedChild}
              />
            ) : (
              <ProfileCard
                key={p.id}
                profile={p}
                colors={colors}
                onEdit={() => setEditing(p)}
                onMakePrimary={() => makePrimaryProfile(p.id)}
                onRemove={() => removeProfile(p.id)}
                restrictedMode={isManagedChild}
              />
            )
          )}
        </View>
      )}

      {/* Privacy — hide for managed child accounts */}
      {!isManagedChild ? <PrivacyCard onDeleteAccount={handleDeleteAccount} /> : null}
    </Screen>
  );
}

// ── DependentCard ─────────────────────────────────────────────────────────────

function DependentCard({ link, profile, colors, onEditProfile, onCreateProfile, onResetPassword }: {
  link: ParentChild;
  profile: PlayerProfile | null;
  colors: any;
  onEditProfile: () => void;
  onCreateProfile: () => void;
  onResetPassword: () => void;
}) {
  const classLabel = profile?.tennis_class ? (TENNIS_CLASS_LABELS[profile.tennis_class] ?? `Classe ${profile.tennis_class}`) : null;
  const levelLabel = profile ? (LEVEL_LABELS[profile.competitive_level] ?? profile.competitive_level) : null;
  const genderLabel = profile?.gender ? (GENDER_LABELS[profile.gender] ?? profile.gender) : null;

  return (
    <Card style={{ marginBottom: 10 }}>
      {/* Child user info */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.accentNeon}22`, borderWidth: 2, borderColor: `${colors.accentNeon}44`, alignItems: 'center', justifyContent: 'center' }}>
          <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 16 }}>
            {(link.child_detail.full_name || 'D').slice(0, 1).toUpperCase()}
          </AppText>
        </View>
        <View style={{ flex: 1 }}>
          <AppText variant="body" style={{ fontWeight: '700', fontSize: 15 }}>{link.child_detail.full_name || '—'}</AppText>
          <AppText variant="caption" style={{ marginTop: 1 }}>{link.child_detail.email}</AppText>
        </View>
      </View>

      {/* Sports profile summary */}
      {profile ? (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.borderSubtle, marginBottom: 10, gap: 4 }}>
          <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 4 }}>Perfil esportivo</AppText>
          {profile.display_name ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="person-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{profile.display_name}</AppText>
            </View>
          ) : null}
          {(profile.birth_year || profile.sporting_age) ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">
                {profile.birth_year ? `Nascimento: ${profile.birth_year}` : ''}
                {profile.sporting_age ? ` • ${profile.sporting_age} anos esportivos` : ''}
              </AppText>
            </View>
          ) : null}
          {genderLabel ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="male-female-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{genderLabel}</AppText>
            </View>
          ) : null}
          {(profile.home_city || profile.home_state) ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="location-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{[profile.home_city, profile.home_state].filter(Boolean).join('/')}</AppText>
            </View>
          ) : null}
          {levelLabel ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="trophy-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{levelLabel}{classLabel ? ` • ${classLabel}` : ''}</AppText>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={{ backgroundColor: `${colors.textMuted}10`, borderRadius: 8, padding: 10, marginBottom: 10, alignItems: 'center' }}>
          <AppText variant="muted" style={{ fontStyle: 'italic' }}>Sem perfil esportivo cadastrado.</AppText>
        </View>
      )}

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {profile ? (
          <Button title="Editar perfil" variant="secondary" onPress={onEditProfile} style={{ flex: 1 }} />
        ) : (
          <Button title="Criar perfil" variant="secondary" onPress={onCreateProfile} style={{ flex: 1 }} />
        )}
        <Button title="Redefinir senha" variant="ghost" onPress={onResetPassword} style={{ flex: 1 }} />
      </View>
    </Card>
  );
}

// ── AddDependentForm ──────────────────────────────────────────────────────────

function AddDependentForm({ onSuccess, onCancel }: { onSuccess: () => Promise<void>; onCancel: () => void }) {
  const { colors } = useTheme();
  const [submitting, setSubmitting] = useState(false);
  const [account, setAccount] = useState({ full_name: '', email: '', password: '', password_confirm: '' });
  const [profile, setProfile] = useState({ birth_year: '', gender: '', home_state: 'SP' });

  async function submit() {
    if (!account.full_name.trim()) return Toast.show({ type: 'error', text1: 'Informe o nome do dependente' });
    if (!account.email.trim()) return Toast.show({ type: 'error', text1: 'Informe o e-mail do dependente' });
    if (!account.password) return Toast.show({ type: 'error', text1: 'Defina uma senha' });
    if (account.password.length < 8) return Toast.show({ type: 'error', text1: 'Senha deve ter no mínimo 8 caracteres' });
    if (account.password !== account.password_confirm) return Toast.show({ type: 'error', text1: 'As senhas não conferem' });

    setSubmitting(true);
    try {
      const link = await createChildAccount({
        full_name: account.full_name.trim(),
        email: account.email.trim().toLowerCase(),
        password: account.password,
        password_confirm: account.password_confirm,
      });

      await createChildProfile(link.id, {
        display_name: account.full_name.trim(),
        birth_year: profile.birth_year ? (Number(profile.birth_year) || undefined) : undefined,
        gender: (profile.gender || '') as any,
        home_state: profile.home_state,
        competitive_level: 'amateur',
        is_primary: true,
      });

      Toast.show({ type: 'success', text1: 'Dependente adicionado!', text2: `${account.full_name} pode fazer login com o e-mail informado.` });
      await onSuccess();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao adicionar dependente', text2: extractApiError(err), visibilityTime: 6000 });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card style={{ marginBottom: 12 }}>
      <AppText variant="body" style={{ fontWeight: '700', marginBottom: 4 }}>Novo dependente</AppText>
      <AppText variant="muted" style={{ marginBottom: 12 }}>
        O dependente poderá fazer login com o e-mail e senha criados abaixo.
      </AppText>

      <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginBottom: 12 }} />
      <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 8 }}>Dados de acesso</AppText>

      <Input
        label="Nome completo"
        value={account.full_name}
        onChangeText={(v) => setAccount({ ...account, full_name: v })}
        placeholder="Nome do dependente"
      />
      <Input
        label="E-mail"
        value={account.email}
        onChangeText={(v) => setAccount({ ...account, email: v })}
        autoCapitalize="none"
        keyboardType="email-address"
        placeholder="email@exemplo.com"
      />
      <Input
        label="Senha inicial"
        value={account.password}
        onChangeText={(v) => setAccount({ ...account, password: v })}
        secureTextEntry
        placeholder="Mínimo 8 caracteres"
      />
      <Input
        label="Confirmar senha"
        value={account.password_confirm}
        onChangeText={(v) => setAccount({ ...account, password_confirm: v })}
        secureTextEntry
        placeholder="Repita a senha"
      />

      <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginTop: 4, marginBottom: 12 }} />
      <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 8 }}>Perfil esportivo (opcional)</AppText>

      <Input
        label="Ano de nascimento"
        value={profile.birth_year}
        onChangeText={(v) => setProfile({ ...profile, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
        keyboardType="number-pad"
        placeholder="Ex: 2010"
      />
      <SelectField
        label="Gênero"
        value={profile.gender}
        options={GENDER_OPTIONS}
        onSelect={(v) => setProfile({ ...profile, gender: v })}
      />
      <SelectField
        label="Estado (UF)"
        value={profile.home_state}
        options={UF_OPTIONS}
        onSelect={(v) => setProfile({ ...profile, home_state: v })}
      />

      <Button title="Adicionar dependente" onPress={submit} loading={submitting} style={{ marginTop: 4 }} />
      <Button title="Cancelar" variant="ghost" onPress={onCancel} />
    </Card>
  );
}

// ── CreateChildProfileForm ────────────────────────────────────────────────────

function CreateChildProfileForm({ link, onSuccess, onCancel }: {
  link: ParentChild;
  onSuccess: () => Promise<void>;
  onCancel: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    display_name: link.child_detail.full_name || '',
    birth_year: '',
    gender: '',
    home_state: 'SP',
    competitive_level: 'amateur',
  });

  async function submit() {
    setSubmitting(true);
    try {
      await createChildProfile(link.id, {
        display_name: form.display_name || link.child_detail.full_name || 'Jogador',
        birth_year: form.birth_year ? Number(form.birth_year) : undefined,
        gender: (form.gender || '') as any,
        home_state: form.home_state,
        competitive_level: form.competitive_level as any,
        is_primary: true,
      });
      Toast.show({ type: 'success', text1: 'Perfil esportivo criado!' });
      await onSuccess();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar perfil', text2: extractApiError(err) });
    } finally {
      setSubmitting(false); }
  }

  return (
    <Card style={{ marginBottom: 10 }}>
      <AppText variant="body" style={{ fontWeight: '700' }}>
        Criar perfil esportivo — {link.child_detail.full_name}
      </AppText>
      <Input
        label="Nome de exibição"
        value={form.display_name}
        onChangeText={(v) => setForm({ ...form, display_name: v })}
      />
      <Input
        label="Ano de nascimento"
        value={form.birth_year}
        onChangeText={(v) => setForm({ ...form, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
        keyboardType="number-pad"
        placeholder="Ex: 2010"
      />
      <SelectField
        label="Gênero"
        value={form.gender}
        options={GENDER_OPTIONS}
        onSelect={(v) => setForm({ ...form, gender: v })}
      />
      <SelectField
        label="Estado (UF)"
        value={form.home_state}
        options={UF_OPTIONS}
        onSelect={(v) => setForm({ ...form, home_state: v })}
      />
      <SelectField
        label="Nível competitivo"
        value={form.competitive_level}
        options={LEVEL_OPTIONS}
        onSelect={(v) => setForm({ ...form, competitive_level: v })}
      />
      <Button title="Criar perfil" onPress={submit} loading={submitting} />
      <Button title="Cancelar" variant="ghost" onPress={onCancel} />
    </Card>
  );
}

// ── PrivacyCard ───────────────────────────────────────────────────────────────

function PrivacyCard({ onDeleteAccount }: { onDeleteAccount: () => void }) {
  const { colors } = useTheme();
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const data = await requestDataExport();
      const jsonString = JSON.stringify(data, null, 2);
      try {
        await Clipboard.setStringAsync(jsonString);
        Toast.show({ type: 'success', text1: 'Dados copiados para a área de transferência.' });
        return;
      } catch {
        // Clipboard unavailable — fallback to Share
      }
      await Share.share({ message: jsonString, title: 'Meus dados Tenfy' });
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

// ── ProfileCard ───────────────────────────────────────────────────────────────

function ProfileCard({ profile: p, colors, onEdit, onMakePrimary, onRemove, restrictedMode = false }: {
  profile: PlayerProfile;
  colors: any;
  onEdit: () => void;
  onMakePrimary: () => void;
  onRemove: () => void;
  restrictedMode?: boolean;
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
            <AppText variant="caption">{[p.home_city, p.home_state].filter(Boolean).join('/')}</AppText>
          </View>
        ) : null}
        {(p.travel_states && p.travel_states.length > 0) ? (
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="map-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">
              {p.travel_states.length >= 27
                ? 'Joga em todo o Brasil'
                : `Joga em: ${p.travel_states.slice(0, 5).join(', ')}${p.travel_states.length > 5 ? ` +${p.travel_states.length - 5}` : ''}`}
            </AppText>
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
          <Ionicons name="trophy-outline" size={13} color={colors.textMuted} />
          <AppText variant="caption">{levelLabel}{classLabel ? ` • ${classLabel}` : ''}</AppText>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
        <Button title="Editar" variant="secondary" onPress={onEdit} style={{ flex: 1 }} />
        {!restrictedMode && !p.is_primary ? <Button title="Selecionar" variant="ghost" onPress={onMakePrimary} style={{ flex: 1 }} /> : null}
        {!restrictedMode ? <Button title="Remover" variant="danger" onPress={onRemove} style={{ flex: p.is_primary ? 2 : 1 }} /> : null}
      </View>
    </Card>
  );
}

// ── ProfileEditor ─────────────────────────────────────────────────────────────

function ProfileEditor({ profile, onSaved, onCancel, restrictedMode = false }: { profile: PlayerProfile; onSaved: () => Promise<void>; onCancel: () => void; restrictedMode?: boolean; }) {
  const [form, setForm] = useState({
    display_name: profile.display_name,
    birth_year: profile.birth_year ? String(profile.birth_year) : '',
    gender: profile.gender ?? '',
    home_state: profile.home_state ?? 'SP',
    home_city: profile.home_city ?? '',
    travel_states: profile.travel_states ?? [],
    tennis_class: profile.tennis_class ?? '',
    competitive_level: profile.competitive_level ?? 'amateur',
  });

  function handleTravelStatesSelect(vals: string[]) {
    if (vals.includes('__ALL__')) {
      setForm((f) => ({ ...f, travel_states: ALL_UFS }));
    } else {
      setForm((f) => ({ ...f, travel_states: vals }));
    }
  }
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
      } as any);
      markProfileDirty();
      Toast.show({ type: 'success', text1: 'Perfil atualizado' });
      await onSaved();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao salvar', text2: extractApiError(err) });
    } finally { setSaving(false); }
  }

  return (
    <Card style={{ marginBottom: 10 }}>
      <AppText variant="body" style={{ fontWeight: '700' }}>Editando: {profile.display_name}</AppText>
      {!restrictedMode ? (
        <Input label="Nome de exibição" value={form.display_name} onChangeText={(v) => setForm({ ...form, display_name: v })} />
      ) : null}
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
      {!restrictedMode ? (
        <>
          <MultiSelectField
            label="Estados onde aceita jogar"
            values={form.travel_states}
            options={TRAVEL_STATE_OPTIONS}
            onSelect={handleTravelStatesSelect}
            placeholder="Selecione os estados..."
            searchable
          />
          <SelectField label="Nível competitivo" value={form.competitive_level} options={LEVEL_OPTIONS} onSelect={(v) => setForm({ ...form, competitive_level: v as PlayerProfile['competitive_level'] })} />
          <SelectField label="Classe" value={form.tennis_class} options={CLASS_OPTIONS} onSelect={(v) => setForm({ ...form, tennis_class: v })} />
        </>
      ) : null}
      <Button title="Salvar alterações" onPress={save} loading={saving} />
      <Button title="Cancelar" variant="ghost" onPress={onCancel} />
    </Card>
  );
}
