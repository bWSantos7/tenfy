import React, { useCallback, useState } from 'react';
import { Image, Linking, Pressable, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { listProfiles } from '../../services/data';
import { myRegistrations } from '../../services/registrations';
import { mediaUrl } from '../../services/api';
import { PlayerProfile, TournamentRegistration } from '../../types';
import { GENDER_LABELS, LEVEL_LABELS, ROLE_LABELS } from '../../utils/format';
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
    .filter((r) => !r.is_withdrawn && ['confirmed', 'waiting_list', 'pending_payment'].includes(r.registration_status))
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
            {user?.avatar
              ? <Image source={{ uri: mediaUrl(user.avatar) }} style={{ width: '100%', height: '100%' }} />
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
              <Card style={{ marginBottom: 12 }}>
                <View style={{ gap: 7 }}>
                  {primary.display_name ? (
                    <Row icon="person-outline" label="Atleta" value={primary.display_name} colors={colors} />
                  ) : null}
                  <Row icon="trophy-outline" label="Nível" value={LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level} colors={colors} />
                  {primary.tennis_class ? (
                    <Row icon="ribbon-outline" label="Classe" value={CLASS_LABELS[primary.tennis_class] ?? primary.tennis_class} colors={colors} />
                  ) : null}
                  {primary.preferred_modality ? (
                    <Row icon="tennisball-outline" label="Modalidade" value={MODALITY_LABELS[primary.preferred_modality] ?? primary.preferred_modality} colors={colors} />
                  ) : null}
                  {primary.gender ? (
                    <Row icon="male-female-outline" label="Gênero" value={GENDER_LABELS[primary.gender] ?? primary.gender} colors={colors} />
                  ) : null}
                  {primary.birth_year ? (
                    <Row icon="calendar-outline" label="Nascimento" value={String(primary.birth_year)} colors={colors} />
                  ) : null}
                  {primary.sporting_age != null ? (
                    <Row icon="time-outline" label="Idade esportiva" value={`${primary.sporting_age} anos`} colors={colors} />
                  ) : null}
                  {(primary.home_city || primary.home_state) ? (
                    <Row icon="location-outline" label="Local" value={[primary.home_city, primary.home_state].filter(Boolean).join(' / ')} colors={colors} />
                  ) : null}
                </View>
              </Card>

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
