import React, { useCallback, useState } from 'react';
import {
  Alert,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import {
  addFamilyMember,
  cancelSubscription,
  fetchPayments,
  fetchSubscription,
  FamilyMember,
  listFamilyMembers,
  Payment,
  reactivateSubscription,
  removeFamilyMember,
  Subscription,
} from '../../services/billing';
import { extractApiError } from '../../services/api';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { useTheme } from '../../contexts/ThemeContext';
import { palette } from '../../theme';

type Nav = NativeStackNavigationProp<MainStackParamList>;

const STATUS_LABELS: Record<string, string> = {
  active:   'Ativa',
  pending:  'Pendente',
  canceled: 'Cancelada',
  expired:  'Expirada',
  unpaid:   'Inadimplente',
  trial:    'Trial',
};

function getStatusColor(status: string, c: typeof palette.dark): string {
  switch (status) {
    case 'active':   return c.statusOpen;
    case 'pending':  return c.statusClosing;
    case 'canceled': return c.statusCanceled;
    case 'expired':  return c.statusClosed;
    case 'unpaid':   return c.statusCanceled;
    case 'trial':    return c.statusProgress;
    default:         return c.textMuted;
  }
}

function formatDate(d: string | null): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR');
}

function formatAmount(amount: string): string {
  return `R$ ${parseFloat(amount).toFixed(2).replace('.', ',')}`;
}

export function SubscriptionScreen() {
  const navigation = useNavigation<Nav>();
  const { colors } = useTheme();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [payments, setPayments]         = useState<Payment[]>([]);
  const [loading, setLoading]           = useState(true);
  const [refreshing, setRefreshing]     = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError]               = useState<string | null>(null);

  const load = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true); else setError(null);
    try {
      const [sub, pays] = await Promise.all([fetchSubscription(), fetchPayments()]);
      setSubscription(sub);
      setPayments(pays.slice(0, 10));
    } catch {
      setError('Não foi possível carregar as informações de assinatura.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => { load(); }, [load]),
  );

  async function handleCancel() {
    Alert.alert(
      'Cancelar assinatura',
      'Deseja cancelar agora ou ao final do período atual?',
      [
        { text: 'Agora',          style: 'destructive', onPress: () => doCancel(true)  },
        { text: 'Fim do período', onPress: () => doCancel(false) },
        { text: 'Não cancelar',   style: 'cancel' },
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
      <Screen scroll={false}>
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <LoadingBlock />
        </View>
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen scroll={false}>
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <EmptyState
            title="Não foi possível carregar"
            subtitle={error}
            icon="cloud-offline-outline"
            action={<Button title="Tentar novamente" onPress={() => { setLoading(true); load(); }} />}
          />
        </View>
      </Screen>
    );
  }

  if (!subscription) {
    return (
      <Screen scroll={false}>
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <EmptyState
            title="Sem assinatura ativa"
            subtitle="Você ainda não possui uma assinatura ativa."
            icon="card-outline"
            action={<Button title="Ver planos disponíveis" onPress={() => navigation.navigate('Plans')} />}
          />
        </View>
      </Screen>
    );
  }

  const sub         = subscription;
  const statusLabel = STATUS_LABELS[sub.status] ?? 'Não informado';
  const statusColor = getStatusColor(sub.status, colors);

  return (
    <Screen onRefresh={() => load(true)} refreshing={refreshing}>
      <AppText variant="section" style={{ marginBottom: 16 }}>Minha assinatura</AppText>

      {/* Current Plan Card */}
      <Card style={{ marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <View style={{ flex: 1, minWidth: 0, paddingRight: 10 }}>
            <AppText variant="section" numberOfLines={2}>{sub.plan_name}</AppText>
            <AppText variant="caption" style={{ marginTop: 2 }}>
              {sub.billing_period === 'yearly' ? 'Cobrança anual' : 'Cobrança mensal'}
            </AppText>
          </View>
          <View style={{ borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4, backgroundColor: statusColor + '20' }}>
            <AppText style={{ fontSize: 12, fontWeight: '700', color: statusColor }}>
              {statusLabel}
            </AppText>
          </View>
        </View>

        <View style={{ height: 1, backgroundColor: colors.borderSubtle, marginBottom: 12 }} />

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
          <AppText variant="muted">Próximo vencimento</AppText>
          <AppText variant="caption" style={{ fontWeight: '600', color: colors.textPrimary }}>
            {formatDate(sub.next_due_date)}
          </AppText>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
          <AppText variant="muted">Início</AppText>
          <AppText variant="caption" style={{ fontWeight: '600', color: colors.textPrimary }}>
            {formatDate(sub.start_date)}
          </AppText>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
          <AppText variant="muted">Valor mensal</AppText>
          <AppText variant="caption" style={{ fontWeight: '600', color: colors.textPrimary }}>
            {formatAmount(sub.price_monthly)}
          </AppText>
        </View>

        {sub.cancel_at_period_end && (
          <View style={{ backgroundColor: `${colors.statusClosing}20`, borderRadius: 8, padding: 10, marginTop: 10 }}>
            <AppText style={{ color: colors.statusClosing, fontSize: 12 }}>
              Cancelamento agendado — ativo até {formatDate(sub.next_due_date)}
            </AppText>
          </View>
        )}
      </Card>

      {/* Pending payment instructions */}
      {sub.status === 'pending' && (
        <Card style={{ marginBottom: 14, borderColor: colors.statusClosing, borderWidth: 1, backgroundColor: `${colors.statusClosing}10` }}>
          <AppText style={{ fontSize: 16, fontWeight: '700', color: colors.statusClosing, marginBottom: 8 }}>
            Pagamento pendente
          </AppText>
          <AppText style={{ fontSize: 13, color: colors.textSecondary, lineHeight: 19, marginBottom: 8 }}>
            Sua assinatura foi criada e está aguardando confirmação do pagamento.
            Verifique seu e-mail para instruções de pagamento (Pix, boleto ou cartão).
          </AppText>
          <AppText style={{ fontSize: 12, color: colors.textMuted, fontStyle: 'italic', marginBottom: 12 }}>
            Após a confirmação do pagamento, sua assinatura será ativada automaticamente.
          </AppText>
          <Button
            title="Reenviar pagamento"
            variant="secondary"
            onPress={() => navigation.navigate('Checkout', {
              plan: {
                id: sub.plan, name: sub.plan_name, slug: sub.plan_slug as any,
                price_monthly: sub.price_monthly, price_yearly: sub.price_yearly,
                description: '', highlight_label: '', display_order: 0,
                is_active: true, max_members: 1, features: [],
              },
              billingPeriod: sub.billing_period,
            })}
          />
        </Card>
      )}

      {/* Actions */}
      <Button
        title="Ver planos / Fazer upgrade"
        onPress={() => navigation.navigate('Plans')}
        style={{ marginBottom: 10 }}
      />

      {sub.is_active && !sub.cancel_at_period_end && (
        <Button
          title="Cancelar assinatura"
          variant="danger"
          loading={actionLoading}
          onPress={handleCancel}
          style={{ marginBottom: 10 }}
        />
      )}

      {sub.cancel_at_period_end && (
        <Button
          title="Manter assinatura"
          loading={actionLoading}
          onPress={handleReactivate}
          style={{ marginBottom: 10 }}
        />
      )}

      {/* Família — gestão de dependentes */}
      {sub.plan_slug === 'familia' && <FamilySection />}

      {/* Payment history */}
      {payments.length > 0 && (
        <>
          <SectionHeader title="Histórico de pagamentos" />
          {payments.map((p) => (
            <Card key={p.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <View style={{ flex: 1, minWidth: 0, paddingRight: 12 }}>
                <AppText variant="caption">{formatDate(p.paid_at ?? p.due_date)}</AppText>
                <AppText variant="body" numberOfLines={2} style={{ fontWeight: '500', marginTop: 2 }}>
                  {p.description || p.payment_method}
                </AppText>
              </View>
              <AppText style={{
                fontSize: 14,
                fontWeight: '700',
                color: p.status === 'paid' ? colors.statusOpen : colors.textMuted,
              }}>
                {formatAmount(p.amount)}
              </AppText>
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

// ── Família — gestão de dependentes ─────────────────────────────────────────

function FamilySection() {
  const { colors } = useTheme();
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail]     = useState('');
  const [adding, setAdding]   = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listFamilyMembers();
      setMembers(data);
    } catch (err: any) {
      Alert.alert('Família', extractApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  async function handleAdd() {
    if (!email.trim()) return;
    setAdding(true);
    try {
      await addFamilyMember({ email: email.trim() });
      setEmail('');
      await load();
    } catch (err: any) {
      Alert.alert('Família', extractApiError(err));
    } finally {
      setAdding(false);
    }
  }

  function handleRemove(m: FamilyMember) {
    Alert.alert(
      'Remover dependente',
      `Remover ${m.member_email} da assinatura?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover', style: 'destructive', onPress: async () => {
            try {
              await removeFamilyMember(m.id);
              await load();
            } catch (err: any) {
              Alert.alert('Família', extractApiError(err));
            }
          },
        },
      ],
    );
  }

  return (
    <Card style={{ marginTop: 16, marginBottom: 4 }}>
      <AppText variant="body" style={{ fontWeight: '700', marginBottom: 4 }}>
        Plano Família — dependentes
      </AppText>
      <AppText variant="muted" style={{ marginBottom: 12 }}>
        Convide pessoas com cadastro no app. O titular é responsável pelo pagamento.
      </AppText>

      <Input
        label="E-mail do dependente"
        value={email}
        onChangeText={setEmail}
        placeholder="email@exemplo.com"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        style={{ marginBottom: 8 }}
      />

      <Button
        title="Adicionar"
        loading={adding}
        disabled={adding || !email.trim()}
        onPress={handleAdd}
        style={{ marginBottom: 12 }}
      />

      {loading ? (
        <LoadingBlock />
      ) : members.length === 0 ? (
        <AppText variant="muted" style={{ textAlign: 'center', paddingVertical: 8 }}>
          Nenhum dependente adicionado.
        </AppText>
      ) : (
        members.map((m) => (
          <View key={m.id} style={{
            flexDirection: 'row', alignItems: 'center',
            paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.borderSubtle,
          }}>
            <View style={{ flex: 1, minWidth: 0, paddingRight: 8 }}>
              <AppText variant="body" numberOfLines={1} style={{ fontWeight: '500' }}>{m.member_email}</AppText>
              <AppText variant="caption" style={{ marginTop: 2 }}>
                {m.status === 'active' ? 'Ativo' : m.status === 'pending' ? 'Aguardando aceite' : 'Removido'}
              </AppText>
            </View>
            <Button
              variant="danger"
              size="small"
              title="Remover"
              onPress={() => handleRemove(m)}
            />
          </View>
        ))
      )}
    </Card>
  );
}
