import React, { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { TournamentRegistration, RegistrationStatus, WatchlistItem, PlayerProfile, ParentChild } from '../../types';
import { myRegistrations, withdrawRegistration } from '../../services/registrations';
import { listChildren, listChildWatchlist, listWatchlist, listProfiles } from '../../services/data';
import { useAuth } from '../../contexts/AuthContext';
import { fmtDateRange } from '../../utils/format';
import { extractApiError } from '../../services/api';

type Props = NativeStackScreenProps<MainStackParamList, 'MyRegistrations'>;

type ThemeColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

function getStatusConfig(c: ThemeColors): Record<string, { color: string; icon: string; bg: string }> {
  return {
    confirmed:       { color: c.statusOpen,    icon: 'checkmark-circle', bg: `${c.statusOpen}20` },
    waiting_list:    { color: c.statusClosing, icon: 'time',             bg: `${c.statusClosing}20` },
    pending_payment: { color: c.accentBlue,    icon: 'card',             bg: `${c.accentBlue}20` },
    withdrawn:       { color: c.statusClosed,  icon: 'close-circle',     bg: `${c.statusClosed}20` },
  };
}

function getPaymentColors(c: ThemeColors): Record<string, string> {
  return {
    paid:     c.statusOpen,
    waived:   c.statusOpen,
    pending:  c.statusClosing,
    refunded: c.statusClosed,
  };
}

interface ChildInscriptionGroup {
  childName: string;
  childId: number;
  items: WatchlistItem[];
}

export function MyRegistrationsScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [withdrawing, setWithdrawing] = useState<number | null>(null);
  const [childGroups, setChildGroups] = useState<ChildInscriptionGroup[]>([]);

  async function buildGroups(): Promise<{ regs: TournamentRegistration[]; groups: ChildInscriptionGroup[] }> {
    const regs = await myRegistrations();
    if (user?.role === 'parent') {
      const children = await listChildren().catch(() => [] as ParentChild[]);
      const childList = children as ParentChild[];
      const childWatchlists = await Promise.all(
        childList.map((link) => listChildWatchlist(link.child).catch(() => [] as WatchlistItem[])),
      );
      const groups: ChildInscriptionGroup[] = childList
        .map((link, i) => ({
          childName: link.child_detail.full_name || link.child_detail.email,
          childId: link.child,
          items: (childWatchlists[i] as WatchlistItem[]).filter((it) => it.user_status === 'registered_declared'),
        }))
        .filter((g) => g.items.length > 0);
      return { regs, groups };
    }
    const [wl, profs] = await Promise.all([listWatchlist(), listProfiles()]);
    const inscribed = (wl as WatchlistItem[]).filter((i) => i.user_status === 'registered_declared');
    const groups: ChildInscriptionGroup[] = inscribed.length > 0
      ? [{ childName: '', childId: 0, items: inscribed }]
      : [];
    return { regs, groups };
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const { regs, groups } = await buildGroups();
      setRegistrations(regs);
      setChildGroups(groups);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const { regs, groups } = await buildGroups();
      setRegistrations(regs);
      setChildGroups(groups);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleWithdraw(reg: TournamentRegistration) {
    setWithdrawing(reg.id);
    try {
      await withdrawRegistration(reg.id);
      Toast.show({ type: 'success', text1: 'Inscrição cancelada.' });
      await load();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Não foi possível cancelar', text2: extractApiError(err) });
    } finally {
      setWithdrawing(null);
    }
  }

  const active = registrations.filter((r) => !r.is_withdrawn);
  const withdrawn = registrations.filter((r) => r.is_withdrawn);
  const totalWatchlistInscribed = childGroups.reduce((acc, g) => acc + g.items.length, 0);

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <AppText variant="section">Minhas Inscrições</AppText>
      </View>

      {loading ? (
        <LoadingBlock />
      ) : error && registrations.length === 0 ? (
        <EmptyState
          icon="cloud-offline-outline"
          title="Não foi possível carregar"
          subtitle={error}
          action={<Button title="Tentar novamente" variant="ghost" onPress={load} />}
        />
      ) : active.length === 0 && withdrawn.length === 0 && totalWatchlistInscribed === 0 ? (
        <EmptyState
          icon="ticket-outline"
          title="Você ainda não tem inscrições"
          subtitle="Na Agenda, marque um torneio como 'Inscrito' para acompanhar aqui."
        />
      ) : (
        <>
          {/* Watchlist-based inscriptions grouped by child */}
          {childGroups.length > 0 && (
            <View>
              <SectionHeader title="Inscrições declaradas" subtitle={`${totalWatchlistInscribed} torneio${totalWatchlistInscribed > 1 ? 's' : ''}`} />
              {childGroups.map((group) => (
                <View key={group.childId || 'self'}>
                  {user?.role === 'parent' ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6, marginTop: 4 }}>
                      <Ionicons name="person-outline" size={14} color={colors.accentBlue} />
                      <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700' }}>{group.childName}</AppText>
                    </View>
                  ) : null}
                  {group.items.map((item) => {
                    const ed = item.edition_detail;
                    return (
                      <Pressable
                        key={`wl-${item.id}`}
                        onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })}
                        style={{ marginBottom: 10 }}
                      >
                        <Card>
                          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                            <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.accentNeon}20`, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                              <Ionicons name="checkmark-circle" size={20} color={colors.accentNeon} />
                            </View>
                            <View style={{ flex: 1 }}>
                              <AppText variant="body" style={{ fontWeight: '700', fontSize: 14 }} numberOfLines={2}>{ed.title}</AppText>
                              {ed.start_date ? (
                                <AppText variant="caption" style={{ color: colors.textMuted, marginTop: 2 }}>
                                  {fmtDateRange(ed.start_date, ed.end_date)}
                                </AppText>
                              ) : null}
                              <View style={{ marginTop: 4, backgroundColor: `${colors.accentNeon}18`, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
                                <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 10 }}>Inscrito</AppText>
                              </View>
                            </View>
                            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                          </View>
                        </Card>
                      </Pressable>
                    );
                  })}
                </View>
              ))}
            </View>
          )}

          {/* Backend official registrations */}
          {active.length > 0 && (
            <View>
              <SectionHeader title="Inscrições oficiais" subtitle={`${active.length} inscrição${active.length > 1 ? 'ões' : ''}`} />
              {active.map((reg) => (
                <RegistrationCard
                  key={reg.id}
                  reg={reg}
                  colors={colors}
                  onPress={() => navigation.navigate('TournamentDetail', { id: reg.edition_id })}
                  onWithdraw={() => handleWithdraw(reg)}
                  withdrawing={withdrawing === reg.id}
                />
              ))}
            </View>
          )}
          {withdrawn.length > 0 && (
            <View>
              <SectionHeader title="Histórico" subtitle="Inscrições canceladas" />
              {withdrawn.map((reg) => (
                <RegistrationCard
                  key={reg.id}
                  reg={reg}
                  colors={colors}
                  onPress={() => navigation.navigate('TournamentDetail', { id: reg.edition_id })}
                />
              ))}
            </View>
          )}
        </>
      )}
    </Screen>
  );
}

function RegistrationCard({ reg, colors, onPress, onWithdraw, withdrawing }: {
  reg: TournamentRegistration;
  colors: ThemeColors;
  onPress: () => void;
  onWithdraw?: () => void;
  withdrawing?: boolean;
}) {
  const STATUS_CONFIG = getStatusConfig(colors);
  const PAYMENT_COLORS = getPaymentColors(colors);
  const sc = STATUS_CONFIG[reg.registration_status] ?? STATUS_CONFIG['pending_payment'];
  const payColor = PAYMENT_COLORS[reg.payment_status] ?? colors.textMuted;

  return (
    <Pressable onPress={onPress} style={{ marginBottom: 10 }}>
      <Card>
        {/* Tournament + status badge */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <AppText variant="body" style={{ fontWeight: '700', flex: 1, marginRight: 8 }} numberOfLines={2}>
            {reg.edition_title}
          </AppText>
          <View style={{ backgroundColor: sc.bg, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name={sc.icon as any} size={12} color={sc.color} />
            <AppText variant="caption" style={{ color: sc.color, fontWeight: '700' }}>{reg.registration_status_label}</AppText>
          </View>
        </View>

        {/* Dates + category */}
        <View style={{ gap: 4 }}>
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
            <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
            <AppText variant="caption">{fmtDateRange(reg.edition_start_date, reg.edition_end_date)}</AppText>
          </View>
          {reg.category_text ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Ionicons name="trophy-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption">{reg.category_text}</AppText>
            </View>
          ) : null}
        </View>

        {/* Position + payment strip */}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {/* Slot position */}
          {reg.slot_position != null && !reg.is_withdrawn ? (
            <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted }}>Posição na lista</AppText>
              <AppText variant="body" style={{ fontWeight: '700', fontSize: 22, color: reg.in_draw ? colors.accentNeon : colors.textPrimary }}>
                #{reg.slot_position}
              </AppText>
              {reg.max_participants ? (
                <AppText variant="caption" style={{ color: reg.in_draw ? colors.accentNeon : colors.danger }}>
                  {reg.in_draw ? `Dentro da chave (${reg.max_participants} vagas)` : `Fora da chave (limite: ${reg.max_participants})`}
                </AppText>
              ) : null}
            </View>
          ) : null}

          {/* Ranking */}
          {reg.ranking_position != null && !reg.is_withdrawn ? (
            <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted }}>Ranking</AppText>
              <AppText variant="body" style={{ fontWeight: '700', fontSize: 22 }}>
                {reg.ranking_position}º
              </AppText>
              <AppText variant="caption">posição no ranking</AppText>
            </View>
          ) : null}

          {/* Payment */}
          {!reg.is_withdrawn ? (
            <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted }}>Pagamento</AppText>
              <Ionicons
                name={reg.payment_status === 'paid' || reg.payment_status === 'waived' ? 'checkmark-circle' : 'time'}
                size={22}
                color={payColor}
                style={{ marginVertical: 2 }}
              />
              <AppText variant="caption" style={{ color: payColor, fontWeight: '600' }}>{reg.payment_status_label}</AppText>
            </View>
          ) : null}
        </View>

        {/* Withdraw button */}
        {!reg.is_withdrawn && onWithdraw ? (
          <Button
            title="Cancelar inscrição"
            variant="danger"
            onPress={onWithdraw}
            loading={withdrawing}
          />
        ) : null}
      </Card>
    </Pressable>
  );
}
