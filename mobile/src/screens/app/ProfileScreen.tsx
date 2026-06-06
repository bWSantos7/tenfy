import React, { useEffect, useRef, useState } from 'react';
import { Alert, FlatList, Image, Modal, Pressable, Share, TextInput, View } from 'react-native';
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
import { deleteAccount, linkExistingChild, uploadAvatar } from '../../services/auth';
import {
  cancelDependentInvite, createChildProfile, createChildWithProfile, deleteProfile, listChildren,
  listChildProfiles, listProfiles, listSentInvites, removeChild, requestDataExport,
  searchPlayersForInvite, sendChildPasswordReset, sendDependentInvite, setPrimary, updateProfile,
  requestChildEmailCode,
} from '../../services/data';
import { extractApiError, mediaUrl } from '../../services/api';
import { DependentInvite, ParentChild, PlayerProfile, PlayerSearchResult } from '../../types';
import { GENDER_LABELS, LEVEL_LABELS, ROLE_LABELS, isValidEmail } from '../../utils/format';
import { markProfileDirty } from '../../utils/profileRefresh';
import { getProfileModality, setProfileModality, MODALITY_OPTIONS } from '../../utils/profileModality';
import { getActiveProfileId, setActiveProfileId } from '../../utils/activeProfile';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader, SelectField } from '../../components/ui';
import { FederationSelect } from '../../components/FederationSelect';

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
  const [activeProfileId, setActiveProfileIdState] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingDep, setEditingDep] = useState<{ link: ParentChild; profile: PlayerProfile } | null>(null);
  const [creatingProfileFor, setCreatingProfileFor] = useState<ParentChild | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [sentInvites, setSentInvites] = useState<DependentInvite[]>([]);

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
        if (user?.id) setActiveProfileIdState(await getActiveProfileId(user.id));
        const invites = await listSentInvites().catch(() => [] as DependentInvite[]);
        setSentInvites(invites.filter((i) => i.status === 'pending'));
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

  function handleRemoveChild(link: ParentChild) {
    Alert.alert(
      'Excluir dependente',
      `Remover ${link.child_detail.full_name || link.child_detail.email} da sua conta?\n\nA conta do dependente continuará existindo, mas você deixará de gerenciá-la.`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Excluir',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeChild(link.id);
              await load();
              Toast.show({ type: 'success', text1: 'Dependente removido.' });
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Erro ao remover dependente', text2: extractApiError(err) });
            }
          },
        },
      ],
    );
  }

  async function handleSelectDependentProfile(profile: PlayerProfile) {
    if (!user?.id) return;
    try {
      await setActiveProfileId(user.id, profile.id);
      setActiveProfileIdState(profile.id);
      markProfileDirty();
      Toast.show({ type: 'success', text1: 'Perfil ativo selecionado.', text2: profile.display_name });
    } catch {
      Toast.show({ type: 'error', text1: 'Não foi possível selecionar o perfil.' });
    }
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
              {(user?.avatar ? mediaUrl(user.avatar) : user?.ti_avatar_url)
                ? <Image source={{ uri: user?.avatar ? mediaUrl(user.avatar) : user?.ti_avatar_url! }} style={{ width: '100%', height: '100%' }} />
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
            <View style={{ flexDirection: 'row', gap: 6, marginLeft: 8 }}>
              <Pressable
                onPress={() => setShowInviteModal(true)}
                style={{ backgroundColor: `${colors.accentBlue}20`, borderWidth: 1, borderColor: `${colors.accentBlue}55`, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', gap: 5, alignItems: 'center' }}
              >
                <Ionicons name="person-add-outline" size={14} color={colors.accentBlue} />
                <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700' }}>Vincular</AppText>
              </Pressable>
              <Pressable
                onPress={() => { setShowAddForm(true); setEditingDep(null); setCreatingProfileFor(null); }}
                style={{ backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}55`, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', gap: 5, alignItems: 'center' }}
              >
                <Ionicons name="add" size={16} color={colors.accentNeon} />
                <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Novo</AppText>
              </Pressable>
            </View>
          </View>

          {showAddForm ? (
            <AddDependentForm
              onSuccess={async () => { setShowAddForm(false); await load(); }}
              onCancel={() => setShowAddForm(false)}
            />
          ) : null}

          {/* Sent invites pending */}
          {sentInvites.length > 0 ? (
            <View style={{ marginBottom: 12 }}>
              <AppText variant="caption" style={{ fontWeight: '700', color: colors.textMuted, marginBottom: 6 }}>Convites enviados aguardando resposta</AppText>
              {sentInvites.map((inv) => (
                <View key={inv.id} style={{ backgroundColor: `${colors.accentBlue}08`, borderWidth: 1, borderColor: `${colors.accentBlue}25`, borderRadius: 12, padding: 10, marginBottom: 6, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.accentBlue}20`, alignItems: 'center', justifyContent: 'center' }}>
                    <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 14 }}>
                      {(inv.invitee_detail.full_name || inv.invitee_detail.email || 'J').slice(0, 1).toUpperCase()}
                    </AppText>
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText variant="caption" style={{ fontWeight: '600' }}>{inv.invitee_detail.full_name || '—'}</AppText>
                    <AppText variant="muted" style={{ fontSize: 11 }}>{inv.invitee_detail.email}</AppText>
                    <AppText variant="muted" style={{ fontSize: 10, marginTop: 1 }}>Aguardando resposta</AppText>
                  </View>
                  <Pressable
                    hitSlop={8}
                    onPress={() => {
                      Alert.alert('Cancelar convite', `Cancelar o convite enviado para ${inv.invitee_detail.full_name || inv.invitee_detail.email}?`, [
                        { text: 'Voltar', style: 'cancel' },
                        {
                          text: 'Cancelar convite', style: 'destructive',
                          onPress: async () => {
                            try {
                              await cancelDependentInvite(inv.id);
                              setSentInvites((prev) => prev.filter((i) => i.id !== inv.id));
                              Toast.show({ type: 'success', text1: 'Convite cancelado.' });
                            } catch (err) {
                              Toast.show({ type: 'error', text1: 'Erro ao cancelar convite', text2: extractApiError(err) });
                            }
                          },
                        },
                      ]);
                    }}
                  >
                    <Ionicons name="close-circle-outline" size={20} color={colors.danger} />
                  </Pressable>
                </View>
              ))}
            </View>
          ) : null}

          {showInviteModal ? (
            <LinkExistingPlayerModal
              onClose={() => setShowInviteModal(false)}
              onInviteSent={(inv) => {
                setSentInvites((prev) => {
                  const already = prev.find((i) => i.id === inv.id);
                  return already ? prev : [inv, ...prev];
                });
                setShowInviteModal(false);
              }}
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
                onSelectProfile={() => profile && handleSelectDependentProfile(profile)}
                onResetPassword={() => handleResetChildPassword(link)}
                onRemove={() => handleRemoveChild(link)}
                isActive={!!profile && activeProfileId === profile.id}
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
            {!isManagedChild && profiles.length === 0 ? (
              <Pressable
                onPress={() => navigation.navigate('Onboarding')}
                style={{ backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}55`, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', gap: 6, alignItems: 'center', marginLeft: 8 }}
              >
                <Ionicons name="add" size={16} color={colors.accentNeon} />
                <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>
                  Criar
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

function DependentCard({ link, profile, colors, onEditProfile, onCreateProfile, onSelectProfile, onResetPassword, onRemove, isActive }: {
  link: ParentChild;
  profile: PlayerProfile | null;
  colors: any;
  onEditProfile: () => void;
  onCreateProfile: () => void;
  onSelectProfile: () => void;
  onResetPassword: () => void;
  onRemove: () => void;
  isActive: boolean;
}) {
  const levelLabel = profile ? (LEVEL_LABELS[profile.competitive_level] ?? profile.competitive_level) : null;
  const genderLabel = profile?.gender ? (GENDER_LABELS[profile.gender] ?? profile.gender) : null;

  return (
    <Card style={{ marginBottom: 10 }}>
      {/* Header: avatar + name/email + active badge */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: `${colors.accentNeon}22`, borderWidth: 2, borderColor: isActive ? colors.accentNeon : `${colors.accentNeon}44`, alignItems: 'center', justifyContent: 'center' }}>
          <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 18 }}>
            {(link.child_detail.full_name || 'D').slice(0, 1).toUpperCase()}
          </AppText>
        </View>
        <View style={{ flex: 1 }}>
          <AppText variant="body" style={{ fontWeight: '700', fontSize: 15 }}>{link.child_detail.full_name || '—'}</AppText>
          <AppText variant="caption" style={{ marginTop: 1, color: colors.textMuted }}>{link.child_detail.email}</AppText>
        </View>
        {isActive ? (
          <View style={{ backgroundColor: `${colors.accentNeon}22`, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: `${colors.accentNeon}55` }}>
            <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Ativo</AppText>
          </View>
        ) : null}
      </View>

      {/* Sports profile summary */}
      {profile ? (
        <View style={{ backgroundColor: `${colors.bgBase}`, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.borderSubtle, marginBottom: 12, gap: 5 }}>
          <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 2 }}>Perfil esportivo</AppText>
          {(profile.birth_year || profile.sporting_age) ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">
                {profile.birth_year ? `Nasc. ${profile.birth_year}` : ''}
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
              <AppText variant="caption">{[profile.home_city, profile.home_state].filter(Boolean).join(' / ')}</AppText>
            </View>
          ) : null}
          {levelLabel ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="trophy-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{levelLabel}</AppText>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={{ borderRadius: 10, padding: 12, marginBottom: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle, borderStyle: 'dashed' }}>
          <Ionicons name="person-add-outline" size={20} color={colors.textMuted} style={{ marginBottom: 4 }} />
          <AppText variant="caption" style={{ color: colors.textMuted }}>Sem perfil esportivo cadastrado</AppText>
        </View>
      )}

      {/* Primary action */}
      <Button
        title={profile ? 'Editar perfil esportivo' : 'Criar perfil esportivo'}
        variant="secondary"
        onPress={profile ? onEditProfile : onCreateProfile}
        style={{ marginBottom: profile && !isActive ? 6 : 0 }}
      />

      {/* Select as active (only when not active and has profile) */}
      {profile && !isActive ? (
        <Button
          title="Selecionar como perfil ativo"
          variant="ghost"
          onPress={onSelectProfile}
        />
      ) : null}

      {/* Secondary actions */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: colors.borderSubtle }}>
        <Pressable
          onPress={onResetPassword}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 4, paddingHorizontal: 6 }}
          hitSlop={8}
        >
          <Ionicons name="key-outline" size={14} color={colors.textMuted} />
          <AppText variant="caption" style={{ color: colors.textMuted }}>Redefinir senha</AppText>
        </Pressable>
        <Pressable
          onPress={onRemove}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 4, paddingHorizontal: 6 }}
          hitSlop={8}
        >
          <Ionicons name="trash-outline" size={14} color={colors.danger} />
          <AppText variant="caption" style={{ color: colors.danger }}>Excluir dependente</AppText>
        </Pressable>
      </View>
    </Card>
  );
}

// ── AddDependentForm ──────────────────────────────────────────────────────────

function AddDependentForm({ onSuccess, onCancel }: { onSuccess: () => Promise<void>; onCancel: () => void }) {
  const { colors } = useTheme();
  const [submitting, setSubmitting] = useState(false);
  const [account, setAccount] = useState({ full_name: '', email: '', password: '', password_confirm: '' });
  const [duplicateEmail, setDuplicateEmail] = useState(false);
  // Task 10: confirmação do e-mail do dependente por código (OTP) antes de criar.
  const [emailCode, setEmailCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);

  async function sendEmailCode() {
    if (!account.email.trim()) return Toast.show({ type: 'error', text1: 'Informe o e-mail do dependente' });
    if (!isValidEmail(account.email)) return Toast.show({ type: 'error', text1: 'E-mail inválido', text2: 'Use o formato nome@dominio.com.' });
    setSendingCode(true);
    setDuplicateEmail(false);
    try {
      await requestChildEmailCode(account.email.trim().toLowerCase());
      setCodeSent(true);
      Toast.show({ type: 'success', text1: 'Código enviado', text2: 'Confira o e-mail do dependente.' });
    } catch (err) {
      const msg = extractApiError(err).toLowerCase();
      if (msg.includes('email') && (msg.includes('existe') || msg.includes('cadastro') || msg.includes('already'))) {
        setDuplicateEmail(true);
      } else {
        Toast.show({ type: 'error', text1: 'Não foi possível enviar o código', text2: extractApiError(err), visibilityTime: 6000 });
      }
    } finally {
      setSendingCode(false);
    }
  }
  const [profile, setProfile] = useState({
    display_name: '',
    birth_year: '',
    gender: '',
    home_state: 'SP',
    home_city: '',
    federation: null as number | null,
    competitive_level: 'pro',
  });
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  useEffect(() => { loadCitiesForState(profile.home_state); }, [profile.home_state]);

  async function loadCitiesForState(uf: string) {
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

  async function submit() {
    if (!account.full_name.trim()) return Toast.show({ type: 'error', text1: 'Informe o nome do dependente' });
    if (!account.email.trim()) return Toast.show({ type: 'error', text1: 'Informe o e-mail do dependente' });
    if (!isValidEmail(account.email)) return Toast.show({ type: 'error', text1: 'E-mail inválido', text2: 'Use o formato nome@dominio.com.' });
    if (!codeSent) return Toast.show({ type: 'error', text1: 'Confirme o e-mail', text2: 'Envie e digite o código enviado ao e-mail do dependente.' });
    if (emailCode.trim().length < 6) return Toast.show({ type: 'error', text1: 'Informe o código de 6 dígitos enviado ao e-mail' });
    if (!account.password) return Toast.show({ type: 'error', text1: 'Defina uma senha' });
    if (account.password.length < 8) return Toast.show({ type: 'error', text1: 'Senha deve ter no mínimo 8 caracteres' });
    if (account.password !== account.password_confirm) return Toast.show({ type: 'error', text1: 'As senhas não conferem' });
    if (!profile.birth_year) return Toast.show({ type: 'error', text1: 'Informe o ano de nascimento do dependente' });
    const birthYearNum = Number(profile.birth_year);
    if (!birthYearNum || birthYearNum < 1940 || birthYearNum > new Date().getFullYear()) {
      return Toast.show({ type: 'error', text1: 'Ano de nascimento inválido' });
    }
    if (!profile.gender) return Toast.show({ type: 'error', text1: 'Selecione o gênero do dependente' });
    if (!profile.home_state) return Toast.show({ type: 'error', text1: 'Selecione o estado do dependente' });
    if (!profile.competitive_level) return Toast.show({ type: 'error', text1: 'Selecione o nível competitivo' });

    setSubmitting(true);
    setDuplicateEmail(false);
    try {
      await createChildWithProfile(
        {
          full_name: account.full_name.trim(),
          email: account.email.trim().toLowerCase(),
          password: account.password,
          password_confirm: account.password_confirm,
          email_code: emailCode.trim(),
        },
        {
          display_name: profile.display_name.trim() || account.full_name.trim(),
          birth_year: birthYearNum,
          gender: profile.gender as 'M' | 'F' | '',
          home_state: profile.home_state,
          home_city: profile.home_city,
          federation: profile.federation,
          competitive_level: profile.competitive_level,
        },
      );
      Toast.show({ type: 'success', text1: 'Dependente adicionado!', text2: `${account.full_name} pode fazer login com o e-mail informado.` });
      await onSuccess();
    } catch (err) {
      const msg = extractApiError(err).toLowerCase();
      const isEmailConflict = msg.includes('email') && (msg.includes('existe') || msg.includes('already') || msg.includes('cadastro') || msg.includes('used'));
      if (isEmailConflict) {
        setDuplicateEmail(true);
      } else {
        Toast.show({ type: 'error', text1: 'Erro ao adicionar dependente', text2: extractApiError(err), visibilityTime: 6000 });
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLinkExisting() {
    setSubmitting(true);
    try {
      const res = await linkExistingChild(account.email.trim().toLowerCase());
      // Backend now returns 202 if invite was sent (requires_invite=true) or 201/200 if link was created
      if ((res as any).requires_invite) {
        Toast.show({
          type: 'info',
          text1: 'Convite enviado!',
          text2: 'O jogador receberá uma notificação para aceitar o vínculo.',
          visibilityTime: 5000,
        });
        setDuplicateEmail(false);
        // Don't call onSuccess — the link isn't created yet, just close the duplicate warning
      } else {
        Toast.show({ type: 'success', text1: 'Dependente vinculado!', text2: 'A conta existente foi vinculada ao seu perfil.' });
        await onSuccess();
      }
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao enviar convite', text2: extractApiError(err), visibilityTime: 6000 });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card style={{ marginBottom: 12 }}>
      <AppText variant="body" style={{ fontWeight: '700', marginBottom: 4 }}>Novo dependente</AppText>
      <AppText variant="muted" style={{ marginBottom: 12 }}>
        Preencha os dados de acesso e o perfil esportivo. Campos com * são obrigatórios.
      </AppText>

      <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginBottom: 12 }} />
      <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 8 }}>Dados de acesso</AppText>

      <Input
        label="Nome completo *"
        value={account.full_name}
        onChangeText={(v) => setAccount({ ...account, full_name: v })}
        placeholder="Nome do dependente"
      />
      <Input
        label="E-mail *"
        value={account.email}
        onChangeText={(v) => { setAccount({ ...account, email: v }); setDuplicateEmail(false); setCodeSent(false); setEmailCode(''); }}
        autoCapitalize="none"
        keyboardType="email-address"
        placeholder="email@exemplo.com"
      />
      <Pressable
        onPress={sendEmailCode}
        disabled={sendingCode || !account.email.trim()}
        style={{ alignSelf: 'flex-start', paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.borderSubtle, marginBottom: 8, opacity: (sendingCode || !account.email.trim()) ? 0.5 : 1 }}
      >
        <AppText variant="caption" style={{ fontWeight: '700', color: colors.accentBlue }}>
          {sendingCode ? 'Enviando...' : (codeSent ? 'Reenviar código' : 'Enviar código de verificação')}
        </AppText>
      </Pressable>
      {codeSent ? (
        <Input
          label="Código de verificação *"
          value={emailCode}
          onChangeText={(v) => setEmailCode(v.replace(/\D/g, '').slice(0, 6))}
          keyboardType="number-pad"
          placeholder="000000"
          maxLength={6}
        />
      ) : null}

      {duplicateEmail ? (
        <View style={{ backgroundColor: `${colors.accentBlue}10`, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: `${colors.accentBlue}35`, marginBottom: 4 }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 10 }}>
            <Ionicons name="information-circle-outline" size={18} color={colors.accentBlue} style={{ marginTop: 1 }} />
            <View style={{ flex: 1 }}>
              <AppText variant="caption" style={{ fontWeight: '700', color: colors.accentBlue }}>Este e-mail já possui uma conta no Tenfy.</AppText>
              <AppText variant="muted" style={{ marginTop: 3, fontSize: 12 }}>
                Envie um convite de vínculo. O jogador receberá uma notificação para aceitar antes de ser vinculado como seu dependente.
              </AppText>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Pressable
              onPress={handleLinkExisting}
              disabled={submitting}
              style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.accentBlue, alignItems: 'center' }}
            >
              <AppText variant="caption" style={{ color: '#fff', fontWeight: '700' }}>
                {submitting ? 'Enviando...' : 'Enviar convite de vínculo'}
              </AppText>
            </Pressable>
            <Pressable
              onPress={() => setDuplicateEmail(false)}
              style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.borderSubtle }}
            >
              <AppText variant="caption">Cancelar</AppText>
            </Pressable>
          </View>
        </View>
      ) : null}

      <Input
        label="Senha inicial *"
        value={account.password}
        onChangeText={(v) => setAccount({ ...account, password: v })}
        secureTextEntry
        placeholder="Mínimo 8 caracteres"
      />
      <Input
        label="Confirmar senha *"
        value={account.password_confirm}
        onChangeText={(v) => setAccount({ ...account, password_confirm: v })}
        secureTextEntry
        placeholder="Repita a senha"
      />

      <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginTop: 4, marginBottom: 12 }} />
      <AppText variant="caption" style={{ fontWeight: '700', color: colors.textSecondary, marginBottom: 8 }}>Perfil esportivo</AppText>

      <Input
        label="Nome do atleta"
        value={profile.display_name}
        onChangeText={(v) => setProfile({ ...profile, display_name: v })}
        placeholder="Deixe em branco para usar o nome completo"
      />
      <Input
        label="Ano de nascimento *"
        value={profile.birth_year}
        onChangeText={(v) => setProfile({ ...profile, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
        keyboardType="number-pad"
        placeholder="Ex: 2010"
      />
      <SelectField
        label="Gênero *"
        value={profile.gender}
        options={GENDER_OPTIONS}
        onSelect={(v) => setProfile({ ...profile, gender: v })}
      />
      <SelectField
        label="Estado (UF) *"
        value={profile.home_state}
        options={UF_OPTIONS}
        onSelect={(v) => setProfile({ ...profile, home_state: v, home_city: '' })}
      />
      <SelectField
        label="Cidade"
        value={profile.home_city}
        options={cities}
        onSelect={(v) => setProfile({ ...profile, home_city: v })}
        placeholder={loadingCities ? 'Carregando...' : 'Selecione a cidade'}
        loading={loadingCities}
        searchable
      />
      <FederationSelect
        value={profile.federation}
        onChange={(id) => setProfile({ ...profile, federation: id })}
      />
      <SelectField
        label="Nível competitivo *"
        value={profile.competitive_level}
        options={LEVEL_OPTIONS}
        onSelect={(v) => setProfile({ ...profile, competitive_level: v })}
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
    home_city: '',
    federation: null as number | null,
    competitive_level: 'pro',
  });
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  useEffect(() => { loadCitiesForState(form.home_state); }, [form.home_state]);

  async function loadCitiesForState(uf: string) {
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

  async function submit() {
    if (!form.birth_year) return Toast.show({ type: 'error', text1: 'Informe o ano de nascimento' });
    const birthYearNum = Number(form.birth_year);
    if (!birthYearNum || birthYearNum < 1940 || birthYearNum > new Date().getFullYear()) {
      return Toast.show({ type: 'error', text1: 'Ano de nascimento inválido' });
    }
    if (!form.gender) return Toast.show({ type: 'error', text1: 'Selecione o gênero' });
    if (!form.competitive_level) return Toast.show({ type: 'error', text1: 'Selecione o nível competitivo' });

    setSubmitting(true);
    try {
      await createChildProfile(link.id, {
        display_name: form.display_name.trim() || link.child_detail.full_name || 'Jogador',
        birth_year: birthYearNum,
        gender: form.gender as any,
        home_state: form.home_state,
        home_city: form.home_city,
        federation: form.federation,
        competitive_level: form.competitive_level as any,
        is_primary: true,
      });
      Toast.show({ type: 'success', text1: 'Perfil esportivo criado!' });
      await onSuccess();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar perfil', text2: extractApiError(err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card style={{ marginBottom: 10 }}>
      <AppText variant="body" style={{ fontWeight: '700', marginBottom: 4 }}>
        Perfil esportivo — {link.child_detail.full_name}
      </AppText>
      <AppText variant="muted" style={{ marginBottom: 10 }}>Campos com * são obrigatórios.</AppText>
      <Input
        label="Nome do atleta"
        value={form.display_name}
        onChangeText={(v) => setForm({ ...form, display_name: v })}
        placeholder="Nome de exibição"
      />
      <Input
        label="Ano de nascimento *"
        value={form.birth_year}
        onChangeText={(v) => setForm({ ...form, birth_year: v.replace(/\D/g, '').slice(0, 4) })}
        keyboardType="number-pad"
        placeholder="Ex: 2010"
      />
      <SelectField
        label="Gênero *"
        value={form.gender}
        options={GENDER_OPTIONS}
        onSelect={(v) => setForm({ ...form, gender: v })}
      />
      <SelectField
        label="Estado (UF) *"
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
      <FederationSelect
        value={form.federation}
        onChange={(id) => setForm({ ...form, federation: id })}
      />
      <SelectField
        label="Nível competitivo *"
        value={form.competitive_level}
        options={LEVEL_OPTIONS}
        onSelect={(v) => setForm({ ...form, competitive_level: v })}
      />
      <Button title="Criar perfil" onPress={submit} loading={submitting} style={{ marginTop: 4 }} />
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
        {p.federation_detail ? (
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="flag-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">
              {p.federation_detail.short_name || p.federation_detail.name}
              {p.federation_detail.state ? ` (${p.federation_detail.state})` : ''}
            </AppText>
          </View>
        ) : (p.travel_states && p.travel_states.length > 0) ? (
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
          <AppText variant="caption">{levelLabel}</AppText>
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

const MOBILE_MODALITY_OPTIONS = MODALITY_OPTIONS.map(({ value, label }) => ({ value, label }));

function ProfileEditor({ profile, onSaved, onCancel, restrictedMode = false }: { profile: PlayerProfile; onSaved: () => Promise<void>; onCancel: () => void; restrictedMode?: boolean; }) {
  const [form, setForm] = useState({
    display_name: profile.display_name,
    birth_year: profile.birth_year ? String(profile.birth_year) : '',
    gender: profile.gender ?? '',
    home_state: profile.home_state ?? 'SP',
    home_city: profile.home_city ?? '',
    federation: profile.federation ?? null,
    competitive_level: profile.competitive_level ?? 'pro',
  });
  const [modality, setModality] = React.useState(profile.preferred_modality ?? '');

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
        preferred_modality: modality,
      } as any);
      await setProfileModality(profile.id, modality);
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
          <FederationSelect
            value={form.federation}
            onChange={(id) => setForm({ ...form, federation: id })}
          />
          <SelectField label="Nível competitivo" value={form.competitive_level} options={LEVEL_OPTIONS} onSelect={(v) => setForm({ ...form, competitive_level: v as PlayerProfile['competitive_level'] })} />
          <SelectField label="Modalidade principal" value={modality} options={MOBILE_MODALITY_OPTIONS} onSelect={setModality} placeholder="Selecione a modalidade" />
        </>
      ) : null}
      <Button title="Salvar alterações" onPress={save} loading={saving} />
      <Button title="Cancelar" variant="ghost" onPress={onCancel} />
    </Card>
  );
}

// ── LinkExistingPlayerModal ────────────────────────────────────────────────────

function LinkExistingPlayerModal({
  onClose,
  onInviteSent,
}: {
  onClose: () => void;
  onInviteSent: (invite: DependentInvite) => void;
}) {
  const { colors } = useTheme();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [sending, setSending] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleQueryChange(text: string) {
    setQuery(text);
    setSearchError(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (text.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await searchPlayersForInvite(text.trim());
        setResults(data);
      } catch (err) {
        setSearchError(extractApiError(err));
      } finally {
        setSearching(false);
      }
    }, 450);
  }

  async function handleSendInvite(player: PlayerSearchResult) {
    setSending(player.id);
    try {
      const invite = await sendDependentInvite(player.id);
      Toast.show({ type: 'success', text1: 'Convite enviado!', text2: `${player.full_name || player.email} receberá uma notificação para aceitar.` });
      onInviteSent(invite);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao enviar convite', text2: extractApiError(err) });
    } finally {
      setSending(null);
    }
  }

  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.bgBase }}>
        {/* Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 20, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
          <Pressable onPress={onClose} hitSlop={10}>
            <Ionicons name="close" size={24} color={colors.textPrimary} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontWeight: '700', fontSize: 17 }}>Vincular jogador existente</AppText>
            <AppText variant="muted" style={{ fontSize: 11 }}>O jogador receberá um convite para aceitar o vínculo</AppText>
          </View>
        </View>

        {/* Search input */}
        <View style={{ paddingHorizontal: 16, paddingVertical: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bgCard, borderRadius: 12, borderWidth: 1, borderColor: colors.borderSubtle, paddingHorizontal: 12, gap: 8 }}>
            <Ionicons name="search-outline" size={18} color={colors.textMuted} />
            <TextInput
              value={query}
              onChangeText={handleQueryChange}
              placeholder="Buscar por nome do jogador..."
              placeholderTextColor={colors.textMuted}
              style={{ flex: 1, height: 44, color: colors.textPrimary, fontSize: 14 }}
              autoFocus
              returnKeyType="search"
            />
            {searching ? (
              <Ionicons name="refresh-outline" size={16} color={colors.textMuted} />
            ) : query.length > 0 ? (
              <Pressable onPress={() => { setQuery(''); setResults([]); }}>
                <Ionicons name="close-circle" size={18} color={colors.textMuted} />
              </Pressable>
            ) : null}
          </View>
          {query.length > 0 && query.length < 2 ? (
            <AppText variant="muted" style={{ fontSize: 11, marginTop: 4 }}>Digite ao menos 2 letras para buscar</AppText>
          ) : null}
        </View>

        {/* Results */}
        {searchError ? (
          <View style={{ paddingHorizontal: 16 }}>
            <AppText variant="caption" style={{ color: colors.danger }}>{searchError}</AppText>
          </View>
        ) : results.length === 0 && query.trim().length >= 2 && !searching ? (
          <View style={{ alignItems: 'center', marginTop: 40, gap: 8 }}>
            <Ionicons name="search-outline" size={32} color={colors.textMuted} />
            <AppText variant="caption" style={{ color: colors.textMuted }}>Nenhum jogador encontrado</AppText>
            <AppText variant="muted" style={{ fontSize: 11, textAlign: 'center', maxWidth: 260 }}>
              Verifique o nome ou peça para o jogador criar uma conta no Tenfy primeiro.
            </AppText>
          </View>
        ) : (
          <FlatList
            data={results}
            keyExtractor={(item) => String(item.id)}
            contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40 }}
            renderItem={({ item }) => (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
                <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: `${colors.accentNeon}22`, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                  {item.avatar
                    ? <Image source={{ uri: mediaUrl(item.avatar) }} style={{ width: 44, height: 44 }} />
                    : <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 16 }}>{(item.full_name || item.email || 'J').slice(0, 1).toUpperCase()}</AppText>
                  }
                </View>
                <View style={{ flex: 1 }}>
                  <AppText variant="body" style={{ fontWeight: '600', fontSize: 14 }}>{item.full_name || '—'}</AppText>
                  <AppText variant="caption" style={{ color: colors.textMuted }}>{item.email}</AppText>
                </View>
                <Pressable
                  onPress={() => handleSendInvite(item)}
                  disabled={sending === item.id}
                  style={{
                    backgroundColor: sending === item.id ? colors.borderSubtle : `${colors.accentBlue}20`,
                    borderWidth: 1,
                    borderColor: sending === item.id ? colors.borderSubtle : `${colors.accentBlue}55`,
                    borderRadius: 10,
                    paddingHorizontal: 12,
                    paddingVertical: 6,
                  }}
                >
                  <AppText variant="caption" style={{ color: sending === item.id ? colors.textMuted : colors.accentBlue, fontWeight: '700' }}>
                    {sending === item.id ? 'Enviando...' : 'Convidar'}
                  </AppText>
                </Pressable>
              </View>
            )}
            ListHeaderComponent={results.length > 0 ? (
              <AppText variant="muted" style={{ fontSize: 11, marginBottom: 8 }}>{results.length} resultado{results.length !== 1 ? 's' : ''} encontrado{results.length !== 1 ? 's' : ''}</AppText>
            ) : null}
          />
        )}
      </View>
    </Modal>
  );
}
