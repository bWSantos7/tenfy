import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import {
  cancelSubscription,
  fetchPayments,
  fetchSubscription,
  Payment,
  reactivateSubscription,
  Subscription,
} from '../../services/billing';

type Nav = NativeStackNavigationProp<MainStackParamList>;

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active:   { label: 'Ativa',        color: '#10B981' },
  pending:  { label: 'Pendente',     color: '#F59E0B' },
  canceled: { label: 'Cancelada',    color: '#EF4444' },
  expired:  { label: 'Expirada',     color: '#6B7280' },
  unpaid:   { label: 'Inadimplente', color: '#EF4444' },
  trial:    { label: 'Trial',        color: '#6366F1' },
};

function formatDate(d: string | null): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR');
}

function formatAmount(amount: string): string {
  return `R$ ${parseFloat(amount).toFixed(2).replace('.', ',')}`;
}

export function SubscriptionScreen() {
  const navigation = useNavigation<Nav>();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const [sub, pays] = await Promise.all([fetchSubscription(), fetchPayments()]);
      setSubscription(sub);
      setPayments(pays.slice(0, 10));
    } catch {
      Alert.alert('Erro', 'Não foi possível carregar as informações.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function handleCancel() {
    Alert.alert(
      'Cancelar assinatura',
      'Deseja cancelar agora ou ao final do período atual?',
      [
        { text: 'Agora',         style: 'destructive', onPress: () => doCancel(true) },
        { text: 'Fim do período', onPress: () => doCancel(false) },
        { text: 'Não cancelar', style: 'cancel' },
      ],
    );
  }

  async function doCancel(immediate: boolean) {
    setActionLoading(true);
    try {
      const updated = await cancelSubscription(immediate);
      setSubscription(updated);
      Alert.alert('Pronto', immediate ? 'Assinatura cancelada.' : 'Cancelamento agendado para o fim do período.');
    } catch {
      Alert.alert('Erro', 'Não foi possível cancelar a assinatura.');
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReactivate() {
    setActionLoading(true);
    try {
      const updated = await reactivateSubscription();
      setSubscription(updated);
      Alert.alert('Pronto', 'Assinatura reativada com sucesso!');
    } catch {
      Alert.alert('Erro', 'Não foi possível reativar a assinatura.');
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#6366F1" />
      </View>
    );
  }

  const sub = subscription!;
  const statusInfo = STATUS_LABELS[sub.status] ?? { label: sub.status, color: '#6B7280' };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />}
    >
      <Text style={styles.title}>Minha assinatura</Text>

      {/* Current Plan Card */}
      <View style={styles.planCard}>
        <View style={styles.planCardRow}>
          <View>
            <Text style={styles.planName}>{sub.plan_name}</Text>
            <Text style={styles.billingPeriod}>
              {sub.billing_period === 'yearly' ? 'Cobrança anual' : 'Cobrança mensal'}
            </Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: statusInfo.color + '20' }]}>
            <Text style={[styles.statusText, { color: statusInfo.color }]}>{statusInfo.label}</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Próximo vencimento</Text>
          <Text style={styles.detailValue}>{formatDate(sub.next_due_date)}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Início</Text>
          <Text style={styles.detailValue}>{formatDate(sub.start_date)}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Valor mensal</Text>
          <Text style={styles.detailValue}>{formatAmount(sub.price_monthly)}</Text>
        </View>

        {sub.cancel_at_period_end && (
          <View style={styles.warningBanner}>
            <Text style={styles.warningText}>
              Cancelamento agendado — ativo até {formatDate(sub.next_due_date)}
            </Text>
          </View>
        )}
      </View>

      {/* Pending payment instructions (M9) */}
      {sub.status === 'pending' && (
        <View style={styles.pendingCard}>
          <Text style={styles.pendingTitle}>⏳ Pagamento pendente</Text>
          <Text style={styles.pendingText}>
            Sua assinatura foi criada e está aguardando confirmação do pagamento.
            Verifique seu e-mail para instruções de pagamento (Pix, boleto ou cartão).
          </Text>
          <Text style={styles.pendingHint}>
            Após a confirmação do pagamento, sua assinatura será ativada automaticamente.
          </Text>
          <TouchableOpacity
            style={styles.retryBtn}
            onPress={() => navigation.navigate('Checkout', {
              plan: { id: sub.plan, name: sub.plan_name, slug: sub.plan_slug as any,
                price_monthly: sub.price_monthly, price_yearly: sub.price_yearly,
                description: '', highlight_label: '', display_order: 0, is_active: true, max_members: 1, features: [] },
              billingPeriod: sub.billing_period,
            })}
          >
            <Text style={styles.retryBtnText}>Reenviar pagamento</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Actions */}
      <TouchableOpacity
        style={styles.upgradeBtn}
        onPress={() => navigation.navigate('Plans')}
      >
        <Text style={styles.upgradeBtnText}>Ver planos / Fazer upgrade</Text>
      </TouchableOpacity>

      {sub.is_active && !sub.cancel_at_period_end && (
        <TouchableOpacity
          style={styles.cancelBtn}
          onPress={handleCancel}
          disabled={actionLoading}
        >
          {actionLoading ? (
            <ActivityIndicator color="#EF4444" />
          ) : (
            <Text style={styles.cancelBtnText}>Cancelar assinatura</Text>
          )}
        </TouchableOpacity>
      )}

      {sub.cancel_at_period_end && (
        <TouchableOpacity
          style={styles.reactivateBtn}
          onPress={handleReactivate}
          disabled={actionLoading}
        >
          {actionLoading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <Text style={styles.reactivateBtnText}>Manter assinatura</Text>
          )}
        </TouchableOpacity>
      )}

      {/* Payment history */}
      {payments.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Histórico de pagamentos</Text>
          {payments.map((p) => (
            <View key={p.id} style={styles.paymentRow}>
              <View>
                <Text style={styles.paymentDate}>{formatDate(p.paid_at ?? p.due_date)}</Text>
                <Text style={styles.paymentDesc}>{p.description || p.payment_method}</Text>
              </View>
              <Text
                style={[
                  styles.paymentAmount,
                  p.status === 'paid' ? styles.amountPaid : styles.amountOther,
                ]}
              >
                {formatAmount(p.amount)}
              </Text>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F8F9FA' },
  content:   { padding: 16, paddingBottom: 40 },
  center:    { flex: 1, justifyContent: 'center', alignItems: 'center' },
  title:     { fontSize: 22, fontWeight: '700', color: '#1F2937', marginBottom: 16 },

  planCard:    { backgroundColor: '#FFF', borderRadius: 14, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: '#E5E7EB' },
  planCardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  planName:    { fontSize: 20, fontWeight: '700', color: '#1F2937' },
  billingPeriod: { fontSize: 12, color: '#6B7280', marginTop: 2 },

  statusBadge: { borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 },
  statusText:  { fontSize: 12, fontWeight: '700' },

  divider:    { height: 1, backgroundColor: '#F3F4F6', marginBottom: 12 },
  detailRow:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  detailLabel:{ fontSize: 13, color: '#6B7280' },
  detailValue:{ fontSize: 13, fontWeight: '600', color: '#1F2937' },

  warningBanner: { backgroundColor: '#FEF3C7', borderRadius: 8, padding: 10, marginTop: 10 },
  warningText:   { color: '#92400E', fontSize: 12 },

  pendingCard:   { backgroundColor: '#FFFBEB', borderRadius: 12, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: '#F59E0B' },
  pendingTitle:  { fontSize: 16, fontWeight: '700', color: '#92400E', marginBottom: 8 },
  pendingText:   { fontSize: 13, color: '#78350F', lineHeight: 19, marginBottom: 8 },
  pendingHint:   { fontSize: 12, color: '#92400E', fontStyle: 'italic', marginBottom: 12 },
  retryBtn:      { backgroundColor: '#F59E0B', borderRadius: 10, paddingVertical: 10, alignItems: 'center' },
  retryBtnText:  { color: '#FFF', fontWeight: '700', fontSize: 14 },

  upgradeBtn:     { backgroundColor: '#6366F1', borderRadius: 12, paddingVertical: 13, alignItems: 'center', marginBottom: 10 },
  upgradeBtnText: { color: '#FFF', fontWeight: '700', fontSize: 15 },

  cancelBtn:     { borderWidth: 1, borderColor: '#EF4444', borderRadius: 12, paddingVertical: 12, alignItems: 'center', marginBottom: 10 },
  cancelBtnText: { color: '#EF4444', fontWeight: '600', fontSize: 14 },

  reactivateBtn:     { backgroundColor: '#10B981', borderRadius: 12, paddingVertical: 13, alignItems: 'center', marginBottom: 10 },
  reactivateBtnText: { color: '#FFF', fontWeight: '700', fontSize: 15 },

  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#1F2937', marginTop: 10, marginBottom: 10 },
  paymentRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#FFF', borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: '#E5E7EB' },
  paymentDate:  { fontSize: 12, color: '#6B7280' },
  paymentDesc:  { fontSize: 13, color: '#374151', fontWeight: '500', marginTop: 2 },
  paymentAmount: { fontSize: 14, fontWeight: '700' },
  amountPaid:    { color: '#10B981' },
  amountOther:   { color: '#6B7280' },
});
