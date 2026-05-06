import React, { useEffect, useState } from 'react';
import { TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { checkout, fetchPlans, fetchSubscription, Plan, Subscription } from '../../services/billing';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen } from '../../components/ui';
import { useTheme } from '../../contexts/ThemeContext';

type Nav = NativeStackNavigationProp<MainStackParamList>;

const PERIOD_LABELS: Record<string, string> = {
  monthly: 'Mensal',
  yearly:  'Anual',
};

function formatPrice(price: string): string {
  const n = parseFloat(price);
  if (n === 0) return 'Grátis';
  return `R$ ${n.toFixed(2).replace('.', ',')}`;
}

function PlanCard({
  plan,
  currentSlug,
  billingPeriod,
  onSelect,
}: {
  plan: Plan;
  currentSlug: string;
  billingPeriod: 'monthly' | 'yearly';
  onSelect: (plan: Plan) => void;
}) {
  const { colors } = useTheme();
  const isCurrent  = plan.slug === currentSlug;
  const price      = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;
  const isHighlighted = Boolean(plan.highlight_label);

  return (
    <Card style={[
      { marginBottom: 18, padding: 18 },
      isHighlighted && { borderColor: colors.accentNeon, borderWidth: 2 },
      isCurrent      && { backgroundColor: `${colors.accentNeon}14` },
    ]}>
      {plan.highlight_label ? (
        <View style={{
          backgroundColor: colors.accentNeon, borderRadius: 20,
          paddingHorizontal: 10, paddingVertical: 3,
          alignSelf: 'flex-start', marginBottom: 8,
        }}>
          <AppText variant="caption" style={{ color: colors.bgBase, fontWeight: '700' }}>
            {plan.highlight_label}
          </AppText>
        </View>
      ) : null}

      <AppText variant="section" style={{ marginBottom: 4 }}>{plan.name}</AppText>

      <View style={{ flexDirection: 'row', alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 4, marginBottom: 8 }}>
        <AppText style={{ fontSize: 30, lineHeight: 44, fontWeight: '800', color: colors.accentNeon }}>
          {formatPrice(price)}
        </AppText>
        {parseFloat(price) > 0 && (
          <AppText variant="muted" style={{ marginLeft: 4, marginBottom: 4, lineHeight: 18 }}>
            {' /'}{billingPeriod === 'yearly' ? 'ano' : 'mês'}
          </AppText>
        )}
      </View>

      {plan.description ? (
        <AppText variant="muted" style={{ marginBottom: 14, lineHeight: 19 }}>{plan.description}</AppText>
      ) : null}

      <View style={{ marginBottom: 16 }}>
        {plan.features.map((f) => (
          <View key={f.code} style={{ flexDirection: 'row', alignItems: 'flex-start', marginBottom: 5 }}>
            <AppText style={{ color: colors.accentNeon, fontWeight: '700', marginRight: 6, fontSize: 14 }}>
              ✓
            </AppText>
            <AppText variant="caption" style={{ flex: 1, lineHeight: 18 }}>
              {f.name}{f.limit != null ? ` (até ${f.limit})` : ''}
            </AppText>
          </View>
        ))}
      </View>

      <Button
        title={isCurrent ? 'Plano atual' : 'Selecionar'}
        variant={isCurrent ? 'secondary' : 'primary'}
        disabled={isCurrent}
        onPress={() => onSelect(plan)}
        style={{ marginTop: 2 }}
      />
    </Card>
  );
}

export function PlansScreen() {
  const navigation   = useNavigation<Nav>();
  const { colors }   = useTheme();
  const [plans, setPlans]           = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchPlans(),
      fetchSubscription().catch(() => null),
    ])
      .then(([p, s]) => {
        setPlans(p);
        if (s) { setSubscription(s); setBillingPeriod(s.billing_period); }
      })
      .catch(() => setError('Não foi possível carregar os planos. Tente novamente.'))
      .finally(() => setLoading(false));
  }, [retryKey]);

  async function handleSelect(plan: Plan) {
    navigation.navigate('Checkout', { plan, billingPeriod });
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
            action={<Button title="Tentar novamente" onPress={() => setRetryKey((k) => k + 1)} />}
          />
        </View>
      </Screen>
    );
  }

  if (plans.length === 0) {
    return (
      <Screen scroll={false}>
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <EmptyState
            title="Nenhum plano disponível"
            subtitle="Não há planos disponíveis no momento."
            icon="pricetag-outline"
            action={<Button title="Voltar" variant="secondary" onPress={() => navigation.goBack()} />}
          />
        </View>
      </Screen>
    );
  }

  const currentSlug = subscription?.plan_slug ?? '';

  return (
    <Screen>
      <AppText variant="section" style={{ textAlign: 'center', marginBottom: 16 }}>
        Escolha seu plano
      </AppText>

      {/* Period toggle */}
      <View style={{
        flexDirection: 'row',
        backgroundColor: colors.bgElevated,
        borderRadius: 10,
        marginBottom: 20,
        padding: 2,
      }}>
        {(['monthly', 'yearly'] as const).map((p) => (
          <TouchableOpacity
            key={p}
            style={[
              { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 9 },
              billingPeriod === p && { backgroundColor: colors.bgCard },
            ]}
            onPress={() => setBillingPeriod(p)}
          >
            <AppText style={{
              fontSize: 13,
              fontWeight: billingPeriod === p ? '600' : '400',
              color: billingPeriod === p ? colors.accentNeon : colors.textMuted,
            }}>
              {PERIOD_LABELS[p]}
            </AppText>
            {p === 'yearly' && (
              <AppText style={{
                fontSize: 11,
                color: billingPeriod === p ? colors.accentNeon : colors.textMuted,
              }}>
                2 meses grátis
              </AppText>
            )}
          </TouchableOpacity>
        ))}
      </View>

      {plans.map((plan) => (
        <PlanCard
          key={plan.id}
          plan={plan}
          currentSlug={currentSlug}
          billingPeriod={billingPeriod}
          onSelect={handleSelect}
        />
      ))}
    </Screen>
  );
}
