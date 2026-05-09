import React, { useEffect, useState } from 'react';
import { TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { checkout, fetchPlans, fetchSubscription, Plan, Subscription } from '../../services/billing';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen } from '../../components/ui';
import { useTheme } from '../../contexts/ThemeContext';

type Nav = NativeStackNavigationProp<MainStackParamList>;

const PERIOD_LABELS: Record<string, string> = {
  monthly: 'Mensal',
  yearly:  'Anual',
};

const PLAN_ICONS: Record<string, string> = {
  individual: 'person-outline',
  familia:    'people-outline',
};

function formatPrice(price: string): string {
  const n = parseFloat(price);
  if (n === 0) return 'Grátis';
  return `R$ ${n.toFixed(2).replace('.', ',')}`;
}

const UNAVAILABLE_PLAN_SLUGS = new Set(['individual', 'familia']);

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
  const isCurrent     = plan.slug === currentSlug;
  const isHighlighted = Boolean(plan.highlight_label);
  const isUnavailable = UNAVAILABLE_PLAN_SLUGS.has(plan.slug);
  const price         = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;
  const icon          = PLAN_ICONS[plan.slug] ?? 'pricetag-outline';

  return (
    <Card style={[
      { marginBottom: 18, padding: 20 },
      isHighlighted && !isUnavailable && { borderColor: colors.accentNeon, borderWidth: 2 },
      isCurrent      && { backgroundColor: `${colors.accentNeon}0e` },
      isUnavailable  && { opacity: 0.6 },
    ]}>
      {/* Badge "Mais popular" or "Em breve" */}
      {isUnavailable ? (
        <View style={{
          backgroundColor: `${colors.textMuted}33`, borderRadius: 20,
          paddingHorizontal: 10, paddingVertical: 3,
          alignSelf: 'flex-start', marginBottom: 12,
        }}>
          <AppText variant="caption" style={{ color: colors.textMuted, fontWeight: '700', fontSize: 11 }}>
            Em breve
          </AppText>
        </View>
      ) : plan.highlight_label ? (
        <View style={{
          backgroundColor: colors.accentNeon, borderRadius: 20,
          paddingHorizontal: 10, paddingVertical: 3,
          alignSelf: 'flex-start', marginBottom: 12,
        }}>
          <AppText variant="caption" style={{ color: colors.bgBase, fontWeight: '700', fontSize: 11 }}>
            {plan.highlight_label}
          </AppText>
        </View>
      ) : null}

      {/* Icon + Plan name row */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <View style={{
          width: 40, height: 40, borderRadius: 20,
          backgroundColor: `${colors.accentNeon}18`,
          alignItems: 'center', justifyContent: 'center',
        }}>
          <Ionicons name={icon as any} size={20} color={colors.accentNeon} />
        </View>
        <View>
          <AppText variant="section">{plan.name}</AppText>
          {/* "Até X perfis" subtitle for Família */}
          {plan.slug === 'familia' && plan.max_members > 1 ? (
            <AppText variant="caption" style={{ color: colors.textMuted, marginTop: 1 }}>
              Até {plan.max_members} perfis na mesma conta
            </AppText>
          ) : null}
        </View>
      </View>

      {/* Price */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginBottom: 16 }}>
        <AppText style={{ fontSize: 32, lineHeight: 40, fontWeight: '900', color: colors.accentNeon }}>
          {formatPrice(price)}
        </AppText>
        {parseFloat(price) > 0 && (
          <AppText variant="muted" style={{ marginLeft: 4, marginBottom: 5, fontSize: 13 }}>
            {' /'}{billingPeriod === 'yearly' ? 'ano' : 'mês'}
          </AppText>
        )}
      </View>

      {/* Feature list */}
      <View style={{ marginBottom: 18, gap: 8 }}>
        {plan.features.map((f) => (
          <View key={f.code} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{
              width: 18, height: 18, borderRadius: 9,
              backgroundColor: `${colors.accentNeon}22`,
              alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Ionicons name="checkmark" size={11} color={colors.accentNeon} />
            </View>
            <AppText variant="caption" style={{ flex: 1, lineHeight: 18 }}>
              {f.name}{f.limit != null ? ` (até ${f.limit})` : ''}
            </AppText>
          </View>
        ))}
      </View>

      <Button
        title={isCurrent ? 'Plano atual' : isUnavailable ? 'Indisponível no momento' : 'Assinar agora'}
        variant={isCurrent || isUnavailable ? 'secondary' : 'primary'}
        disabled={isCurrent || isUnavailable}
        onPress={isUnavailable ? undefined : () => onSelect(plan)}
      />
    </Card>
  );
}

export function PlansScreen() {
  const navigation   = useNavigation<Nav>();
  const { colors }   = useTheme();
  const [plans, setPlans]                   = useState<Plan[]>([]);
  const [subscription, setSubscription]     = useState<Subscription | null>(null);
  const [billingPeriod, setBillingPeriod]   = useState<'monthly' | 'yearly'>('monthly');
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState<string | null>(null);
  const [retryKey, setRetryKey]             = useState(0);

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
      <AppText variant="title" style={{ textAlign: 'center', marginBottom: 4 }}>
        Nossos planos
      </AppText>
      <AppText variant="muted" style={{ textAlign: 'center', marginBottom: 20 }}>
        Escolha o plano ideal para você e sua família
      </AppText>

      {/* Period toggle */}
      <View style={{
        flexDirection: 'row',
        backgroundColor: colors.bgCard,
        borderRadius: 12,
        marginBottom: 24,
        padding: 3,
        borderWidth: 1,
        borderColor: colors.borderSubtle,
      }}>
        {(['monthly', 'yearly'] as const).map((p) => (
          <TouchableOpacity
            key={p}
            style={[
              { flex: 1, paddingVertical: 9, alignItems: 'center', borderRadius: 10 },
              billingPeriod === p && { backgroundColor: colors.accentNeon },
            ]}
            onPress={() => setBillingPeriod(p)}
          >
            <AppText style={{
              fontSize: 13,
              fontWeight: '600',
              color: billingPeriod === p ? colors.bgBase : colors.textMuted,
            }}>
              {PERIOD_LABELS[p]}
            </AppText>
            {p === 'yearly' && (
              <AppText style={{
                fontSize: 10,
                fontWeight: '600',
                color: billingPeriod === p ? colors.bgBase : colors.accentNeon,
                marginTop: 1,
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
