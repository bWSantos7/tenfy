import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { checkout, fetchPlans, fetchSubscription, Plan, Subscription } from '../../services/billing';

type Nav = NativeStackNavigationProp<MainStackParamList>;

const PERIOD_LABELS: Record<string, string> = {
  monthly: 'Mensal',
  yearly: 'Anual',
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
  const isCurrent = plan.slug === currentSlug;
  const price = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;
  const isHighlighted = Boolean(plan.highlight_label);

  return (
    <View style={[styles.card, isHighlighted && styles.cardHighlighted, isCurrent && styles.cardCurrent]}>
      {plan.highlight_label ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{plan.highlight_label}</Text>
        </View>
      ) : null}
      <Text style={styles.planName}>{plan.name}</Text>
      <Text style={styles.planPrice}>
        {formatPrice(price)}
        {parseFloat(price) > 0 && (
          <Text style={styles.pricePeriod}> /{billingPeriod === 'yearly' ? 'ano' : 'mês'}</Text>
        )}
      </Text>
      {plan.description ? <Text style={styles.planDesc}>{plan.description}</Text> : null}

      <View style={styles.featureList}>
        {plan.features.map((f) => (
          <View key={f.code} style={styles.featureRow}>
            <Text style={styles.featureCheck}>✓</Text>
            <Text style={styles.featureName}>
              {f.name}
              {f.limit != null ? ` (até ${f.limit})` : ''}
            </Text>
          </View>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.selectBtn, isCurrent && styles.selectBtnCurrent]}
        onPress={() => onSelect(plan)}
        disabled={isCurrent}
      >
        <Text style={styles.selectBtnText}>{isCurrent ? 'Plano atual' : 'Selecionar'}</Text>
      </TouchableOpacity>
    </View>
  );
}

export function PlansScreen() {
  const navigation = useNavigation<Nav>();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#6366F1" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.feedbackText}>{error}</Text>
        <TouchableOpacity style={styles.selectBtn} onPress={() => setRetryKey((k) => k + 1)}>
          <Text style={styles.selectBtnText}>Tentar novamente</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (plans.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.feedbackText}>Nenhum plano disponível no momento.</Text>
        <TouchableOpacity style={[styles.selectBtn, { backgroundColor: '#6B7280' }]} onPress={() => navigation.goBack()}>
          <Text style={styles.selectBtnText}>Voltar</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const currentSlug = subscription?.plan_slug ?? '';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Escolha seu plano</Text>

      <View style={styles.periodToggle}>
        {(['monthly', 'yearly'] as const).map((p) => (
          <TouchableOpacity
            key={p}
            style={[styles.periodBtn, billingPeriod === p && styles.periodBtnActive]}
            onPress={() => setBillingPeriod(p)}
          >
            <Text style={[styles.periodBtnText, billingPeriod === p && styles.periodBtnTextActive]}>
              {PERIOD_LABELS[p]}
              {p === 'yearly' ? '  (2 meses grátis)' : ''}
            </Text>
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
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F8F9FA' },
  content:   { padding: 16, paddingBottom: 40 },
  center:    { flex: 1, justifyContent: 'center', alignItems: 'center' },
  feedbackText: { color: '#6B7280', textAlign: 'center', marginBottom: 16, paddingHorizontal: 24, lineHeight: 20 },
  title:     { fontSize: 24, fontWeight: '700', color: '#1F2937', marginBottom: 16, textAlign: 'center' },

  periodToggle: { flexDirection: 'row', backgroundColor: '#E5E7EB', borderRadius: 10, marginBottom: 20, padding: 2 },
  periodBtn:    { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 9 },
  periodBtnActive:     { backgroundColor: '#FFFFFF' },
  periodBtnText:       { fontSize: 13, color: '#6B7280' },
  periodBtnTextActive: { color: '#6366F1', fontWeight: '600' },

  card:            { backgroundColor: '#FFF', borderRadius: 14, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: '#E5E7EB' },
  cardHighlighted: { borderColor: '#6366F1', borderWidth: 2 },
  cardCurrent:     { backgroundColor: '#F0F0FF' },

  badge:     { backgroundColor: '#6366F1', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start', marginBottom: 8 },
  badgeText: { color: '#FFF', fontSize: 11, fontWeight: '700' },

  planName:  { fontSize: 20, fontWeight: '700', color: '#1F2937', marginBottom: 4 },
  planPrice: { fontSize: 26, fontWeight: '800', color: '#6366F1', marginBottom: 6 },
  pricePeriod: { fontSize: 14, fontWeight: '400', color: '#6B7280' },
  planDesc:  { fontSize: 13, color: '#6B7280', marginBottom: 12 },

  featureList: { marginBottom: 16 },
  featureRow:  { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 5 },
  featureCheck:{ color: '#10B981', fontWeight: '700', marginRight: 6, fontSize: 14 },
  featureName: { fontSize: 13, color: '#374151', flex: 1 },

  selectBtn:        { backgroundColor: '#6366F1', borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  selectBtnCurrent: { backgroundColor: '#D1D5DB' },
  selectBtnText:    { color: '#FFF', fontWeight: '700', fontSize: 15 },
});
