import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Alert as RNAlert, Image, Linking, Modal, Pressable, TextInput, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import Toast from 'react-native-toast-message';
import { fetchTiData, linkUtr, listProfiles, searchUtr, syncTiData, syncUtr, unlinkUtr } from '../../services/data';
import { myRegistrations } from '../../services/registrations';
import { extractApiError, mediaUrl } from '../../services/api';
import { CatalogRanking, PlayerProfile, TiData, TiRankingEntry, TournamentRegistration, UtrCandidate } from '../../types';
import { GENDER_LABELS, LEVEL_LABELS, ROLE_LABELS } from '../../utils/format';
import { editionCountry } from '../../utils/country';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';

type Props = BottomTabScreenProps<MainTabParamList, 'Profile'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;

const SOURCE_LABELS: Record<string, string> = {
  cbt: 'CBT – Confederação Brasileira de Tênis',
  fpt: 'FPT SP – Federação Paulista',
  fbt: 'FBT – Federação Baiana',
  fct: 'FCT – Federação Cearense',
  cosat: 'COSAT',
  itf: 'ITF',
  utr: 'UTR',
};

const MODALITY_LABELS: Record<string, string> = {
  tennis: 'Tênis',
  beach_tennis: 'Beach Tennis',
  padel: 'Padel',
  wheelchair: 'Tênis em cadeira de rodas',
};

const CLASS_LABELS: Record<string, string> = {
  '1': 'Classe 1', '2': 'Classe 2', '3': 'Classe 3',
  '4': 'Classe 4', '5': 'Classe 5', 'PR': 'PR', 'PRO': 'PRO',
};

function extractTiId(value: unknown): string | null {
  if (!value) return null;
  const s = String(value);
  const m = s.match(/^tenisintegrado:(\d+)$/) || (!s.includes(':') && s.match(/^(\d+)$/));
  return m ? m[1] : null;
}

export function PlayerProfileScreen(_: Props) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const navigation = useNavigation<StackNav>();

  const [loading, setLoading] = useState(true);
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(false);
  const [tiSyncing, setTiSyncing] = useState(false);

  // UTR modal state
  const [utrModalVisible, setUtrModalVisible] = useState(false);
  const [utrQuery, setUtrQuery] = useState('');
  const [utrSearching, setUtrSearching] = useState(false);
  const [utrCandidates, setUtrCandidates] = useState<UtrCandidate[]>([]);
  const [utrSearchError, setUtrSearchError] = useState('');
  const [utrLinking, setUtrLinking] = useState(false);
  const [utrSyncing, setUtrSyncing] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      (async () => {
        setLoading(true);
        try {
          const [profs, regs] = await Promise.all([
            listProfiles().catch(() => [] as PlayerProfile[]),
            myRegistrations().catch(() => [] as TournamentRegistration[]),
          ]);
          if (!active) return;
          setProfiles(profs as PlayerProfile[]);
          setRegistrations(regs);

          // Load TI data for primary profile
          const primary = (profs as PlayerProfile[]).find((p) => p.is_primary) ?? (profs as PlayerProfile[])[0];
          if (primary) {
            setTiLoading(true);
            fetchTiData(primary.id).then((d) => { if (active) setTiData(d); }).catch(() => {}).finally(() => { if (active) setTiLoading(false); });
          }
        } finally {
          if (active) setLoading(false);
        }
      })();
      return () => { active = false; };
    }, []),
  );

  const primary = profiles.find((p) => p.is_primary) ?? profiles[0] ?? null;
  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role ?? ''] ?? user?.role ?? '';

  // Extract Tênis Integrado linked IDs
  const tiLinks: { source: string; tiId: string }[] = [];
  if (primary?.external_ids) {
    for (const [src, val] of Object.entries(primary.external_ids)) {
      const tiId = extractTiId(val);
      if (tiId) tiLinks.push({ source: src, tiId });
    }
  }

  // Active/upcoming registrations (not withdrawn)
  const activeRegs = registrations
    .filter((r) => !r.is_withdrawn && !r.is_past && ['confirmed', 'waiting_list', 'pending_payment'].includes(r.registration_status))
    .slice(0, 5);

  return (
    <Screen>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
        <View style={{ flex: 1 }}>
          <AppText variant="title">Perfil</AppText>
        </View>
        <Pressable
          onPress={() => navigation.navigate('Settings')}
          hitSlop={10}
          style={{ padding: 6, borderRadius: 10, backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.borderSubtle }}
        >
          <Ionicons name="settings-outline" size={20} color={colors.textSecondary} />
        </Pressable>
      </View>

      {/* ── User card ──────────────────────────────────────────────── */}
      <Card style={{ marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: `${colors.accentNeon}22`, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: `${colors.accentNeon}44` }}>
            {(user?.avatar ? mediaUrl(user.avatar) : user?.ti_avatar_url)
              ? <Image source={{ uri: user?.avatar ? mediaUrl(user.avatar) : user?.ti_avatar_url! }} style={{ width: '100%', height: '100%' }} />
              : <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '800', fontSize: 24 }}>{avatarLetter}</AppText>
            }
          </View>
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontWeight: '700', fontSize: 18 }}>{user?.full_name || '—'}</AppText>
            <AppText variant="caption" style={{ color: colors.textMuted, marginTop: 1 }}>{user?.email}</AppText>
            <View style={{ flexDirection: 'row', gap: 6, marginTop: 5, flexWrap: 'wrap' }}>
              <View style={{ backgroundColor: `${colors.accentBlue}22`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>{roleLabel}</AppText>
              </View>
              {primary && (
                <View style={{ backgroundColor: `${colors.accentNeon}18`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                  <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '600' }}>
                    {LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level}
                  </AppText>
                </View>
              )}
            </View>
          </View>
        </View>
      </Card>

      {loading ? <LoadingBlock /> : (
        <>
          {/* ── Sem perfil ─────────────────────────────────────────── */}
          {!primary ? (
            <Card style={{ marginBottom: 12 }}>
              <EmptyState
                icon="person-outline"
                title="Perfil esportivo não configurado"
                subtitle="Complete seu perfil para ver torneios compatíveis e suas informações de jogador."
                action={<Button title="Completar perfil" variant="secondary" onPress={() => navigation.navigate('Onboarding')} />}
              />
            </Card>
          ) : (
            <>
              {/* ── Perfil esportivo ───────────────────────────────── */}
              <SectionHeader title="Perfil esportivo" />
              <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden', marginBottom: 12 }}>

                {/* Name + location */}
                <View style={{ paddingHorizontal: 16, paddingTop: 14, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
                  <AppText style={{ fontSize: 18, fontWeight: '800', color: colors.textPrimary }}>{primary.display_name || '—'}</AppText>
                  {(primary.home_city || primary.home_state) ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                      <Ionicons name="location-outline" size={12} color={colors.textMuted} />
                      <AppText variant="muted" style={{ fontSize: 12 }}>{[primary.home_city, primary.home_state].filter(Boolean).join(' / ')}</AppText>
                    </View>
                  ) : null}
                </View>

                {/* Key attributes grid */}
                <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
                  {[
                    { label: 'Nível',      value: LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level },
                    { label: 'Modalidade', value: primary.preferred_modality ? (MODALITY_LABELS[primary.preferred_modality] ?? primary.preferred_modality) : '—' },
                    { label: 'Gênero',     value: primary.gender ? (GENDER_LABELS[primary.gender] ?? primary.gender) : '—' },
                  ].map((item, i) => (
                    <View
                      key={item.label}
                      style={{ flex: 1, alignItems: 'center', paddingVertical: 12, borderRightWidth: i < 2 ? 1 : 0, borderRightColor: colors.borderSubtle }}
                    >
                      <AppText style={{ fontSize: 13, fontWeight: '700', color: colors.textPrimary, textAlign: 'center' }} numberOfLines={1}>{item.value}</AppText>
                      <AppText variant="muted" style={{ fontSize: 10, marginTop: 2 }}>{item.label}</AppText>
                    </View>
                  ))}
                </View>

                {/* Secondary info */}
                <View style={{ paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  {primary.birth_year ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                      <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
                      <AppText variant="muted" style={{ fontSize: 12 }}>
                        Nasc. {primary.birth_year}{primary.sporting_age != null ? ` (${primary.sporting_age} anos)` : ''}
                      </AppText>
                    </View>
                  ) : null}
                  {primary.tennis_class ? (
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20, backgroundColor: `${colors.accentNeon}18`, borderWidth: 1, borderColor: `${colors.accentNeon}30` }}>
                      <AppText style={{ fontSize: 11, color: colors.accentNeon, fontWeight: '700' }}>
                        {CLASS_LABELS[primary.tennis_class] ?? `Classe ${primary.tennis_class}`}
                      </AppText>
                    </View>
                  ) : null}
                </View>

              </View>

              {/* ── Categorias ────────────────────────────────────── */}
              {primary.categories?.length > 0 ? (
                <>
                  <SectionHeader title="Categorias compatíveis" />
                  <Card style={{ marginBottom: 12 }}>
                    {primary.categories.slice(0, 8).map((cat, i) => (
                      <View
                        key={cat.id}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: i < Math.min(primary.categories.length, 8) - 1 ? 1 : 0, borderBottomColor: colors.borderSubtle }}
                      >
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: cat.is_primary ? colors.accentNeon : colors.textMuted }} />
                        <AppText variant="caption" style={{ flex: 1 }}>
                          {cat.category_detail?.label_ptbr ?? cat.category_detail?.code ?? `Cat. ${cat.category}`}
                        </AppText>
                        {cat.is_primary ? (
                          <View style={{ backgroundColor: `${colors.accentNeon}18`, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
                            <AppText variant="muted" style={{ fontSize: 9, color: colors.accentNeon }}>Principal</AppText>
                          </View>
                        ) : null}
                      </View>
                    ))}
                  </Card>
                </>
              ) : null}

              {/* ── Rankings (Tênis Integrado) ────────────────────── */}
              {(tiLoading || (tiData && tiData.has_ti_id)) ? (
                <>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <AppText variant="section">Rankings</AppText>
                    {tiData?.ti_id ? (
                      <Pressable
                        disabled={tiSyncing}
                        hitSlop={8}
                        onPress={async () => {
                          if (!primary) return;
                          setTiSyncing(true);
                          try {
                            await syncTiData(primary.id);
                            const fresh = await fetchTiData(primary.id);
                            setTiData(fresh);
                          } catch { /* ignore */ } finally { setTiSyncing(false); }
                        }}
                      >
                        <Ionicons name={tiSyncing ? 'refresh' : 'refresh-outline'} size={16} color={tiSyncing ? colors.accentNeon : colors.textMuted} />
                      </Pressable>
                    ) : null}
                  </View>

                  {tiLoading ? (
                    <Card style={{ marginBottom: 12 }}>
                      <AppText variant="muted" style={{ textAlign: 'center', paddingVertical: 8 }}>Carregando rankings...</AppText>
                    </Card>
                  ) : (tiData?.rankings && tiData.rankings.length > 0) || (tiData?.catalog_rankings && tiData.catalog_rankings.length > 0) ? (
                    <>
                      {tiData?.rankings && tiData.rankings.length > 0 ? (
                        <RankingsMobile
                          rankings={tiData.rankings}
                          isStale={!!tiData.is_stale}
                          colors={colors}
                          showFederativos={!(tiData?.catalog_rankings && tiData.catalog_rankings.length > 0)}
                        />
                      ) : null}
                      <CatalogRankingsMobile rankings={tiData?.catalog_rankings ?? []} colors={colors} />
                    </>
                  ) : tiData?.has_ti_id ? (
                    <Card style={{ marginBottom: 12 }}>
                      <AppText variant="muted" style={{ textAlign: 'center', paddingVertical: 8 }}>Nenhum ranking encontrado para este perfil.</AppText>
                    </Card>
                  ) : null}
                </>
              ) : null}

              {/* ── UTR Rating ────────────────────────────────────── */}
              <UtrSection
                profile={primary}
                utrSyncing={utrSyncing}
                colors={colors}
                onOpenModal={() => {
                  setUtrQuery(primary.display_name || '');
                  setUtrCandidates([]);
                  setUtrSearchError('');
                  setUtrModalVisible(true);
                }}
                onSync={async () => {
                  if (!primary) return;
                  setUtrSyncing(true);
                  try {
                    await syncUtr(primary.id);
                    const profs = await listProfiles();
                    setProfiles(profs as PlayerProfile[]);
                  } catch { /* ignore */ } finally { setUtrSyncing(false); }
                }}
                onUnlink={() => {
                  RNAlert.alert(
                    'Remover rating UTR?',
                    'O rating UTR e o vínculo com este perfil serão removidos do seu perfil esportivo. Você poderá vincular novamente depois.',
                    [
                      { text: 'Cancelar', style: 'cancel' },
                      {
                        text: 'Confirmar exclusão', style: 'destructive',
                        onPress: async () => {
                          if (!primary) return;
                          try {
                            await unlinkUtr(primary.id);
                            const profs = await listProfiles();
                            setProfiles(profs as PlayerProfile[]);
                            Toast.show({ type: 'success', text1: 'Rating UTR removido do perfil.' });
                          } catch (err) {
                            Toast.show({
                              type: 'error',
                              text1: 'Não foi possível remover o rating UTR',
                              text2: extractApiError(err),
                            });
                          }
                        },
                      },
                    ],
                  );
                }}
              />

              {/* ── Modal de busca UTR ────────────────────────────── */}
              <Modal
                visible={utrModalVisible}
                animationType="slide"
                presentationStyle="pageSheet"
                onRequestClose={() => setUtrModalVisible(false)}
              >
                <View style={{ flex: 1, backgroundColor: colors.bgBase, padding: 20 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 20 }}>
                    <AppText variant="title" style={{ flex: 1 }}>Vincular perfil UTR</AppText>
                    <Pressable onPress={() => setUtrModalVisible(false)} hitSlop={10}>
                      <Ionicons name="close" size={24} color={colors.textSecondary} />
                    </Pressable>
                  </View>

                  <AppText variant="caption" style={{ marginBottom: 12, color: colors.textMuted }}>
                    Busque seu nome na UTR e confirme qual perfil é o seu.
                  </AppText>

                  <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
                    <TextInput
                      value={utrQuery}
                      onChangeText={setUtrQuery}
                      placeholder="Nome do atleta..."
                      placeholderTextColor={colors.textMuted}
                      style={{
                        flex: 1, backgroundColor: colors.bgCard, color: colors.textPrimary,
                        borderWidth: 1, borderColor: colors.borderSubtle, borderRadius: 10,
                        paddingHorizontal: 14, paddingVertical: 10, fontSize: 14,
                      }}
                      autoCapitalize="words"
                      returnKeyType="search"
                      onSubmitEditing={async () => {
                        if (!primary || utrQuery.trim().length < 2) return;
                        setUtrSearching(true);
                        setUtrSearchError('');
                        setUtrCandidates([]);
                        try {
                          const result = await searchUtr(primary.id, utrQuery.trim());
                          setUtrCandidates(result.candidates);
                          if (result.candidates.length === 0) setUtrSearchError('Nenhum perfil encontrado. Tente outro nome.');
                        } catch { setUtrSearchError('Não foi possível buscar. Verifique sua conexão.'); }
                        finally { setUtrSearching(false); }
                      }}
                    />
                    <Pressable
                      onPress={async () => {
                        if (!primary || utrQuery.trim().length < 2) return;
                        setUtrSearching(true);
                        setUtrSearchError('');
                        setUtrCandidates([]);
                        try {
                          const result = await searchUtr(primary.id, utrQuery.trim());
                          setUtrCandidates(result.candidates);
                          if (result.candidates.length === 0) setUtrSearchError('Nenhum perfil encontrado. Tente outro nome.');
                        } catch { setUtrSearchError('Não foi possível buscar. Verifique sua conexão.'); }
                        finally { setUtrSearching(false); }
                      }}
                      style={{ backgroundColor: colors.accentNeon, borderRadius: 10, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' }}
                    >
                      {utrSearching
                        ? <ActivityIndicator size="small" color="#000" />
                        : <Ionicons name="search" size={18} color="#000" />}
                    </Pressable>
                  </View>

                  {utrSearchError ? (
                    <AppText variant="muted" style={{ color: colors.danger, marginBottom: 8 }}>{utrSearchError}</AppText>
                  ) : null}

                  {utrCandidates.map((c) => (
                    <View
                      key={c.utr_player_id}
                      style={{ backgroundColor: colors.bgCard, borderRadius: 12, borderWidth: 1, borderColor: colors.borderSubtle, padding: 14, marginBottom: 10 }}
                    >
                      <AppText style={{ fontWeight: '700', fontSize: 15, color: colors.textPrimary, marginBottom: 2 }}>{c.display_name}</AppText>
                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                        {c.country ? <AppText variant="muted" style={{ fontSize: 11 }}>{c.country}</AppText> : null}
                        {c.location ? <AppText variant="muted" style={{ fontSize: 11 }}>• {c.location}</AppText> : null}
                        {c.gender ? <AppText variant="muted" style={{ fontSize: 11 }}>• {c.gender}</AppText> : null}
                      </View>
                      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 10 }}>
                        {c.singles_utr ? (
                          <View>
                            <AppText style={{ fontSize: 20, fontWeight: '900', color: colors.accentNeon }}>{c.singles_utr}</AppText>
                            <AppText variant="muted" style={{ fontSize: 10 }}>Simples</AppText>
                          </View>
                        ) : null}
                        {c.doubles_utr ? (
                          <View>
                            <AppText style={{ fontSize: 20, fontWeight: '900', color: colors.accentBlue }}>{c.doubles_utr}</AppText>
                            <AppText variant="muted" style={{ fontSize: 10 }}>Duplas</AppText>
                          </View>
                        ) : null}
                        {!c.singles_utr && !c.doubles_utr ? (
                          <AppText variant="muted" style={{ fontSize: 12, fontStyle: 'italic' }}>Rating extraído automaticamente após confirmar.</AppText>
                        ) : null}
                      </View>
                      <AppText variant="muted" style={{ fontSize: 10, marginBottom: 8 }}>ID: {c.utr_player_id}</AppText>
                      <Button
                        title={utrLinking ? 'Vinculando...' : 'Este sou eu — vincular'}
                        variant="secondary"
                        onPress={async () => {
                          if (!primary || utrLinking) return;
                          setUtrLinking(true);
                          try {
                            await linkUtr(primary.id, c);
                            const profs = await listProfiles();
                            setProfiles(profs as PlayerProfile[]);
                            setUtrModalVisible(false);
                          } catch {
                            setUtrSearchError('Falha ao vincular. Tente novamente.');
                          } finally { setUtrLinking(false); }
                        }}
                      />
                    </View>
                  ))}
                </View>
              </Modal>

              {/* ── Vínculos com Tênis Integrado ──────────────────── */}
              {tiLinks.length > 0 ? (
                <>
                  <SectionHeader title="Vínculos externos" />
                  <Card style={{ marginBottom: 12 }}>
                    {tiLinks.map((link, i) => (
                      <Pressable
                        key={link.source}
                        onPress={() => Linking.openURL(`https://www.tenisintegrado.com.br/perfil2/index/${link.tiId}`)}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: i < tiLinks.length - 1 ? 1 : 0, borderBottomColor: colors.borderSubtle }}
                      >
                        <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.accentBlue}18`, alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name="link-outline" size={18} color={colors.accentBlue} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <AppText variant="caption" style={{ fontWeight: '600' }}>{SOURCE_LABELS[link.source] ?? link.source.toUpperCase()}</AppText>
                          <AppText variant="muted" style={{ fontSize: 11 }}>ID: {link.tiId} • Tênis Integrado</AppText>
                        </View>
                        <Ionicons name="open-outline" size={16} color={colors.textMuted} />
                      </Pressable>
                    ))}
                    <AppText variant="muted" style={{ fontSize: 10, marginTop: 8 }}>
                      Toque para visualizar seu perfil na plataforma de origem.
                    </AppText>
                  </Card>
                </>
              ) : null}
            </>
          )}

          {/* ── Inscrições ativas ─────────────────────────────────── */}
          {activeRegs.length > 0 ? (
            <>
              <SectionHeader
                title="Inscrições ativas"
                action={
                  <Pressable onPress={() => navigation.navigate('MyRegistrations')} hitSlop={8}>
                    <AppText variant="caption" style={{ color: colors.accentBlue }}>Ver todas</AppText>
                  </Pressable>
                }
              />
              <Card style={{ marginBottom: 12 }}>
                {activeRegs.map((reg, i) => (
                  <View
                    key={reg.id}
                    style={{ paddingVertical: 10, borderBottomWidth: i < activeRegs.length - 1 ? 1 : 0, borderBottomColor: colors.borderSubtle, gap: 3 }}
                  >
                    <AppText variant="caption" style={{ fontWeight: '600', fontSize: 13 }} numberOfLines={2}>
                      {reg.edition_title}
                    </AppText>
                    <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', marginTop: 2 }}>
                      {reg.category_text ? (
                        <View style={{ backgroundColor: `${colors.accentNeon}15`, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
                          <AppText variant="muted" style={{ fontSize: 10 }}>{reg.category_text}</AppText>
                        </View>
                      ) : null}
                      <RegistrationStatusBadge status={reg.registration_status} colors={colors} />
                    </View>
                    {reg.edition_start_date ? (
                      <AppText variant="muted" style={{ fontSize: 11 }}>
                        {new Date(reg.edition_start_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </AppText>
                    ) : null}
                    {(() => {
                      const c = editionCountry({ venue_country: reg.edition_venue_country, venue_country_code: reg.edition_venue_country_code });
                      const loc = c
                        ? [reg.edition_venue_city, c.name].filter(Boolean).join(', ')
                        : [reg.edition_venue_city, reg.edition_venue_state].filter(Boolean).join(' / ');
                      if (!loc) return null;
                      return (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 }}>
                          {c?.flagUrl ? (
                            <Image source={{ uri: c.flagUrl }} style={{ width: 15, height: 11, borderRadius: 2 }} />
                          ) : (
                            <Ionicons name="location-outline" size={11} color={colors.textMuted} />
                          )}
                          <AppText variant="muted" style={{ fontSize: 11 }}>{loc}</AppText>
                        </View>
                      );
                    })()}
                  </View>
                ))}
              </Card>
            </>
          ) : registrations.length === 0 && !loading ? (
            <>
              <SectionHeader title="Inscrições" />
              <Card style={{ marginBottom: 12 }}>
                <AppText variant="caption" style={{ color: colors.textMuted, textAlign: 'center', paddingVertical: 8 }}>
                  Nenhuma inscrição encontrada.
                </AppText>
                <Button
                  title="Ver torneios"
                  variant="ghost"
                  onPress={() => navigation.navigate('Tabs', { screen: 'Tournaments' } as never)}
                />
              </Card>
            </>
          ) : null}
        </>
      )}
    </Screen>
  );
}

function Row({ icon, label, value, colors }: { icon: string; label: string; value: string; colors: any }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Ionicons name={icon as any} size={14} color={colors.textMuted} style={{ width: 16 }} />
      <AppText variant="muted" style={{ fontSize: 12, width: 90 }}>{label}</AppText>
      <AppText variant="caption" style={{ flex: 1, fontWeight: '500' }}>{value}</AppText>
    </View>
  );
}

// ── RankingsMobile ────────────────────────────────────────────────────────────

/** True when a points string ("0.00", "0,00", "", "200.25") represents zero / no standing. */
function pointsAreZero(p?: string): boolean {
  if (!p) return true;
  const n = parseFloat(String(p).replace(/\./g, '').replace(',', '.'));
  return !isNaN(n) && n === 0;
}

function RankingsMobile({ rankings, isStale, colors, showFederativos = true }: { rankings: TiRankingEntry[]; isStale: boolean; colors: any; showFederativos?: boolean }) {
  const wtn = rankings.filter((r) => r.federation === 'World Tennis Number');
  // Fallback only (avoid duplicating "Rankings CBT / Federações"); hide zero points.
  const fed = showFederativos
    ? rankings.filter((r) => r.federation !== 'World Tennis Number' && !pointsAreZero(r.points))
    : [];

  return (
    <View style={{ gap: 10, marginBottom: 12 }}>
      {/* WTN block */}
      {wtn.length > 0 && (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: `${colors.bgElevated}CC`, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
            <Ionicons name="globe-outline" size={13} color={colors.accentBlue} />
            <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 12 }}>WTN — World Tennis Number</AppText>
          </View>
          <View style={{ flexDirection: 'row' }}>
            {wtn.map((r, i) => (
              <View
                key={i}
                style={{ flex: 1, alignItems: 'center', paddingVertical: 16, borderRightWidth: i < wtn.length - 1 ? 1 : 0, borderRightColor: colors.borderSubtle }}
              >
                <AppText style={{ fontSize: 28, fontWeight: '900', color: colors.textPrimary }}>{r.points ?? '—'}</AppText>
                <AppText variant="muted" style={{ fontSize: 11, marginTop: 2 }}>{r.modality || r.category}</AppText>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Federation rankings */}
      {fed.length > 0 && (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden' }}>
          <View style={{ paddingHorizontal: 14, paddingVertical: 10, backgroundColor: `${colors.bgElevated}CC`, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
            <AppText variant="muted" style={{ fontWeight: '700', fontSize: 11 }}>Rankings federativos</AppText>
          </View>
          {fed.map((r, i) => {
            const pos = r.position ? Number(r.position) : null;
            const posColor = pos === 1 ? '#FFD700' : pos === 2 ? '#C0C0C0' : pos === 3 ? '#CD7F32' : colors.accentNeon;
            return (
              <View
                key={i}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: i === 0 ? 0 : 1, borderTopColor: colors.borderSubtle }}
              >
                {/* Position box */}
                <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: pos ? `${posColor}18` : colors.bgElevated, borderWidth: 1, borderColor: pos ? `${posColor}40` : colors.borderSubtle, alignItems: 'center', justifyContent: 'center' }}>
                  {pos ? (
                    <AppText style={{ fontSize: 14, fontWeight: '900', color: posColor }}>{pos}º</AppText>
                  ) : (
                    <AppText variant="muted" style={{ fontSize: 12 }}>—</AppText>
                  )}
                </View>

                {/* Name + federation + date */}
                <View style={{ flex: 1 }}>
                  <AppText variant="caption" style={{ fontWeight: '600', fontSize: 13, lineHeight: 18 }} numberOfLines={2}>
                    {r.ranking_name || r.category || '—'}
                  </AppText>
                  <View style={{ flexDirection: 'row', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                    {r.federation ? (
                      <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 20, backgroundColor: `${colors.accentBlue}20` }}>
                        <AppText variant="muted" style={{ fontSize: 10, color: colors.accentBlue, fontWeight: '600' }}>{r.federation}</AppText>
                      </View>
                    ) : null}
                    {r.date ? <AppText variant="muted" style={{ fontSize: 10 }}>{r.date}</AppText> : null}
                  </View>
                </View>

                {/* Points */}
                {r.points ? (
                  <View style={{ alignItems: 'flex-end' }}>
                    <AppText style={{ fontSize: 16, fontWeight: '900', color: colors.textPrimary }}>{r.points}</AppText>
                    <AppText variant="muted" style={{ fontSize: 9 }}>pontos</AppText>
                  </View>
                ) : null}
              </View>
            );
          })}
        </View>
      )}

      {isStale && (
        <AppText variant="muted" style={{ fontSize: 10, textAlign: 'center' }}>Dados podem estar desatualizados. Toque em ↻ para atualizar.</AppText>
      )}
    </View>
  );
}

// ── CatalogRankingsMobile ──────────────────────────────────────────────────────
// Structured rankings imported into Tenfy's local catalogue (CBT / state
// federations via Tênis Integrado). Purely additive — does not touch UTR.

function CatalogRankingsMobile({ rankings, colors }: { rankings: CatalogRanking[]; colors: any }) {
  if (!rankings || rankings.length === 0) return null;

  return (
    <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden', marginBottom: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: `${colors.bgElevated}CC`, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
        <Ionicons name="trophy-outline" size={13} color={colors.accentBlue} />
        <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 12 }}>Rankings CBT / Federações</AppText>
      </View>

      {rankings.map((r, i) => {
        const pos = r.position ?? null;
        const posColor = pos === 1 ? '#FFD700' : pos === 2 ? '#C0C0C0' : pos === 3 ? '#CD7F32' : colors.accentNeon;
        return (
          <View
            key={r.id ?? i}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: i === 0 ? 0 : 1, borderTopColor: colors.borderSubtle }}
          >
            {/* Position box */}
            <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: pos ? `${posColor}18` : colors.bgElevated, borderWidth: 1, borderColor: pos ? `${posColor}40` : colors.borderSubtle, alignItems: 'center', justifyContent: 'center' }}>
              {pos ? (
                <AppText style={{ fontSize: 14, fontWeight: '900', color: posColor }}>{pos}º</AppText>
              ) : (
                <AppText variant="muted" style={{ fontSize: 12 }}>—</AppText>
              )}
            </View>

            {/* Ranking name + category + federation */}
            <View style={{ flex: 1 }}>
              <AppText variant="caption" style={{ fontWeight: '600', fontSize: 13, lineHeight: 18 }} numberOfLines={2}>
                {r.ranking_name || r.category || '—'}
              </AppText>
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                {r.federation ? (
                  <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 20, backgroundColor: `${colors.accentBlue}20` }}>
                    <AppText variant="muted" style={{ fontSize: 10, color: colors.accentBlue, fontWeight: '600' }}>{r.federation}</AppText>
                  </View>
                ) : null}
                {r.category ? <AppText variant="muted" style={{ fontSize: 10 }}>{r.category}</AppText> : null}
                {r.season ? <AppText variant="muted" style={{ fontSize: 10 }}>· {r.season}</AppText> : null}
              </View>
            </View>

            {/* Points */}
            {r.points ? (
              <View style={{ alignItems: 'flex-end' }}>
                <AppText style={{ fontSize: 16, fontWeight: '900', color: colors.textPrimary }}>{r.points}</AppText>
                <AppText variant="muted" style={{ fontSize: 9 }}>pontos</AppText>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

// ── UtrSection ───────────────────────────────────────────────────────────────

function UtrSection({
  profile, utrSyncing, colors, onOpenModal, onSync, onUnlink,
}: {
  profile: PlayerProfile;
  utrSyncing: boolean;
  colors: any;
  onOpenModal: () => void;
  onSync: () => void;
  onUnlink: () => void;
}) {
  const hasUtr = !!profile.utr_player_id;

  return (
    <>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, marginTop: 4 }}>
        <AppText variant="section">UTR Rating</AppText>
        {hasUtr ? (
          <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
            <Pressable onPress={onSync} disabled={utrSyncing} hitSlop={8}>
              <Ionicons name={utrSyncing ? 'refresh' : 'refresh-outline'} size={16} color={utrSyncing ? colors.accentNeon : colors.textMuted} />
            </Pressable>
            <Pressable onPress={onUnlink} hitSlop={8}>
              <Ionicons name="unlink-outline" size={16} color={colors.textMuted} />
            </Pressable>
          </View>
        ) : null}
      </View>

      {hasUtr ? (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden', marginBottom: 12 }}>
          {/* Header UTR */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: `${colors.bgElevated}CC`, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
            <Ionicons name="tennisball-outline" size={13} color={colors.accentNeon} />
            <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 12 }}>UTR — Universal Tennis Rating</AppText>
          </View>

          {/* Ratings row */}
          <View style={{ flexDirection: 'row' }}>
            <View style={{ flex: 1, alignItems: 'center', paddingVertical: 18, borderRightWidth: 1, borderRightColor: colors.borderSubtle }}>
              <AppText style={{ fontSize: 28, fontWeight: '900', color: colors.textPrimary }}>
                {profile.utr_singles || '—'}
              </AppText>
              <AppText variant="muted" style={{ fontSize: 11, marginTop: 2 }}>Simples</AppText>
            </View>
            <View style={{ flex: 1, alignItems: 'center', paddingVertical: 18 }}>
              <AppText style={{ fontSize: 28, fontWeight: '900', color: colors.textPrimary }}>
                {profile.utr_doubles || '—'}
              </AppText>
              <AppText variant="muted" style={{ fontSize: 11, marginTop: 2 }}>Duplas</AppText>
            </View>
          </View>

          {/* Footer */}
          <View style={{ paddingHorizontal: 14, paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.borderSubtle, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <AppText variant="muted" style={{ fontSize: 10 }}>
              {profile.utr_display_name || `ID: ${profile.utr_player_id}`}
            </AppText>
            {profile.utr_profile_url ? (
              <Pressable onPress={() => Linking.openURL(profile.utr_profile_url)} hitSlop={8}>
                <Ionicons name="open-outline" size={13} color={colors.accentBlue} />
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, borderWidth: 1, borderColor: colors.borderSubtle, padding: 14, marginBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <Ionicons name="tennisball-outline" size={20} color={colors.textMuted} />
          <View style={{ flex: 1 }}>
            <AppText variant="caption" style={{ fontWeight: '600', marginBottom: 1 }}>UTR não vinculado</AppText>
            <AppText variant="muted" style={{ fontSize: 11 }}>
              Vincule seu perfil UTR para exibir seu rating.
            </AppText>
          </View>
          <Pressable
            onPress={onOpenModal}
            hitSlop={8}
            style={{ backgroundColor: `${colors.accentNeon}18`, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: `${colors.accentNeon}33` }}
          >
            <AppText style={{ fontSize: 11, color: colors.accentNeon, fontWeight: '700' }}>Vincular</AppText>
          </Pressable>
        </View>
      )}
    </>
  );
}

function RegistrationStatusBadge({ status, colors }: { status: string; colors: any }) {
  const cfg: Record<string, { label: string; color: string }> = {
    confirmed: { label: 'Confirmado', color: colors.statusOpen },
    waiting_list: { label: 'Lista de espera', color: colors.statusClosing },
    pending_payment: { label: 'Pagamento pendente', color: colors.statusClosing },
    withdrawn: { label: 'Desistiu', color: colors.danger },
  };
  const c = cfg[status] ?? { label: status, color: colors.textMuted };
  return (
    <View style={{ backgroundColor: `${c.color}18`, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
      <AppText variant="muted" style={{ fontSize: 10, color: c.color }}>{c.label}</AppText>
    </View>
  );
}
