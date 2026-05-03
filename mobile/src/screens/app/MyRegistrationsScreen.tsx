import React, { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { TournamentRegistration, RegistrationStatus } from '../../types';
import { myRegistrations, withdrawRegistration } from '../../services/registrations';
import { fmtDateRange } from '../../utils/format';
import { extractApiError } from '../../services/api';

type Props = NativeStackScreenProps<MainStackParamList, 'MyRegistrations'>;

const STATUS_CONFIG: Record<RegistrationStatus, { color: string; icon: string; bg: string }> = {
  confirmed: { color: '#39ff14', icon: 'checkmark-circle', bg: '#39ff1420' },
  waiting_list: { color: '#f59e0b', icon: 'time', bg: '#f59e0b20' },
  pending_payment: { color: '#3b82f6', icon: 'card', bg: '#3b82f620' },
  withdrawn: { color: '#6b7280', icon: 'close-circle', bg: '#6b728020' },
};

const PAYMENT_COLORS: Record<string, string> = {
  paid: '#39ff14',
  waived: '#39ff14',
  pending: '#f59e0b',
  refunded: '#6b7280',
};

export function MyRegistrationsScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [withdrawing, setWithdrawing] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setRegistrations(await myRegistrations());
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
      setRegistrations(await myRegistrations());
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
      ) : active.length === 0 && withdrawn.length === 0 ? (
        <EmptyState
          icon="ticket-outline"
          title="Você ainda não tem inscrições"
          subtitle="Quando se inscrever em um torneio, suas inscrições aparecerão aqui."
        />
      ) : (
        <>
          {active.length > 0 && (
            <View>
              <SectionHeader title="Inscrições ativas" subtitle={`${active.length} inscrição${active.length > 1 ? 'ões' : ''}`} />
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
  colors: any;
  onPress: () => void;
  onWithdraw?: () => void;
  withdrawing?: boolean;
}) {
  const sc = STATUS_CONFIG[reg.registration_status] ?? STATUS_CONFIG.pending_payment;
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
                <AppText variant="caption" style={{ color: reg.in_draw ? colors.accentNeon : '#ef4444' }}>
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
