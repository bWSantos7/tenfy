import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { checkout, CheckoutPayload } from '../../services/billing';
import { tokenizeCard, getAsaasCustomerId } from '../../services/asaas';
import api from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';

type CheckoutRouteProp = RouteProp<MainStackParamList, 'Checkout'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

type PaymentMethod = 'pix' | 'credit_card' | 'debit_card';

const METHOD_CONFIG: Record<PaymentMethod, { label: string; icon: string; description: string }> = {
  pix:         { label: 'Pix',               icon: '⚡', description: 'Aprovação instantânea' },
  credit_card: { label: 'Cartão de crédito', icon: '💳', description: 'Parcelamento disponível' },
  debit_card:  { label: 'Cartão de débito',  icon: '🏦', description: 'Débito imediato' },
};

function formatCardNumber(value: string): string {
  return value.replace(/\D/g, '').slice(0, 16).replace(/(.{4})/g, '$1 ').trim();
}

function formatExpiry(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 4);
  if (digits.length >= 3) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return digits;
}

function formatPrice(price: string, period: 'monthly' | 'yearly'): string {
  const n = parseFloat(price);
  if (n === 0) return 'Grátis';
  return `R$ ${n.toFixed(2).replace('.', ',')} / ${period === 'yearly' ? 'ano' : 'mês'}`;
}

export function CheckoutScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<CheckoutRouteProp>();
  const { plan, billingPeriod } = route.params;
  const { user } = useAuth();
  const { colors } = useTheme();

  const [method, setMethod] = useState<PaymentMethod>('pix');
  const [loading, setLoading] = useState(false);

  // Credit card fields
  const [cardName, setCardName]       = useState('');
  const [cardNumber, setCardNumber]   = useState('');
  const [expiry, setExpiry]           = useState('');
  const [ccv, setCcv]                 = useState('');
  const [cpf, setCpf]                 = useState('');
  const [cep, setCep]                 = useState('');

  const price = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;

  function validateCard(): string | null {
    if (!cardName.trim())               return 'Informe o nome no cartão.';
    if (cardNumber.replace(/\s/g, '').length < 16) return 'Número do cartão inválido.';
    if (expiry.length < 5)              return 'Informe a validade (MM/AA).';
    if (ccv.length < 3)                 return 'CVV inválido.';
    if (cpf.replace(/\D/g, '').length < 11) return 'CPF inválido.';
    if (cep.replace(/\D/g, '').length < 8)  return 'CEP inválido.';
    return null;
  }

  async function handleConfirm() {
    if (method === 'credit_card' || method === 'debit_card') {
      const err = validateCard();
      if (err) { Alert.alert('Dados incompletos', err); return; }
    }

    setLoading(true);
    try {
      const isCard = method === 'credit_card' || method === 'debit_card';

      // PCI-DSS: tokenize card directly with Asaas — raw card data never hits our backend
      let cardToken: string | undefined;
      if (isCard) {
        const customerId = await getAsaasCustomerId(api, 0);
        if (!customerId) {
          Alert.alert('Erro', 'Serviço de pagamento indisponível. Tente novamente.');
          setLoading(false);
          return;
        }
        const [expiryMonth, expiryYear] = expiry.split('/');
        try {
          const tokenResult = await tokenizeCard(
            {
              holderName:  cardName.trim(),
              number:      cardNumber.replace(/\s/g, ''),
              expiryMonth: expiryMonth,
              expiryYear:  expiryYear,
              ccv,
            },
            {
              name:       cardName.trim(),
              email:      user?.email || '',
              cpfCnpj:    cpf.replace(/\D/g, ''),
              postalCode: cep.replace(/\D/g, ''),
            },
            customerId,
          );
          cardToken = tokenResult.creditCardToken;
        } catch (tokenErr: any) {
          const msg = tokenErr?.response?.data?.errors?.[0]?.description
            || 'Dados do cartão inválidos. Verifique e tente novamente.';
          Alert.alert('Erro no cartão', msg);
          setLoading(false);
          return;
        }
      }

      const payload: CheckoutPayload = {
        plan_slug:      plan.slug as 'individual' | 'familia',
        billing_period: billingPeriod,
        payment_method: method,
        // Only the token is sent — card number/CVV stay on the device
        ...(isCard && cardToken ? { card_token: cardToken } : {}),
      };

      const result = await checkout(payload);

      if (method === 'pix') {
        if (result.pix?.copia_e_cola || result.pix?.qr_code_image) {
          // Navigate to Pix screen — subscription activates ONLY after webhook confirms
          navigation.replace('PixPayment', { pixData: result.pix! });
        } else {
          Alert.alert(
            'Pix indisponível',
            'A cobrança ficou pendente, mas o Asaas não retornou o QR Code. Tente novamente em instantes.',
          );
        }
      } else if (isCard) {
        const msg = result.status === 'active' && !result.pending_plan
          ? 'Pagamento aprovado! Sua assinatura está ativa.'
          : 'Assinatura criada. Aguardando confirmação do pagamento.';
        Alert.alert('Concluído', msg, [
          { text: 'OK', onPress: () => navigation.navigate('Subscription') },
        ]);
      } else {
        navigation.navigate('Subscription');
      }
    } catch (err: any) {
      let msg = 'Não foi possível processar o pagamento.';
      if (!err?.response) {
        msg = 'Sem conexão com a internet. Verifique sua rede e tente novamente.';
      } else if (err.response.status >= 500) {
        msg = 'Erro interno no servidor. Tente novamente em alguns minutos.';
      } else if (err.response.status === 422 || err.response.status === 400) {
        msg = err.response.data?.detail ?? 'Dados inválidos. Verifique as informações.';
      } else if (err.response.status === 402) {
        msg = 'Pagamento recusado. Verifique os dados do cartão ou escolha outro método.';
      } else if (err.response.data?.detail) {
        msg = err.response.data.detail;
      }
      Alert.alert('Erro no pagamento', msg);
    } finally {
      setLoading(false);
    }
  }

  const inp = {
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.textPrimary,
    marginBottom: 10,
  } as const;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.bgBase }}
        contentContainerStyle={{ padding: 20, paddingBottom: 40 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={{ fontSize: 22, fontWeight: '700', color: colors.textPrimary, marginBottom: 20 }}>
          Finalizar assinatura
        </Text>

        {/* Summary */}
        <View style={{ backgroundColor: colors.accentBlue, borderRadius: 14, padding: 20, marginBottom: 24 }}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: 14, marginBottom: 4 }}>{plan.name}</Text>
          <Text style={{ color: '#FFF', fontSize: 26, fontWeight: '800' }}>{formatPrice(price, billingPeriod)}</Text>
          {billingPeriod === 'yearly' && (
            <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginTop: 6 }}>
              Equivale a R$ {(parseFloat(price) / 12).toFixed(2).replace('.', ',')}/mês — 2 meses grátis
            </Text>
          )}
        </View>

        {/* Payment method */}
        {(
          <>
            <Text style={{ fontSize: 15, fontWeight: '600', color: colors.textSecondary, marginBottom: 10, marginTop: 8 }}>
              Forma de pagamento
            </Text>
            {(Object.keys(METHOD_CONFIG) as PaymentMethod[]).map((m) => {
              const cfg = METHOD_CONFIG[m];
              const selected = method === m;
              return (
                <TouchableOpacity
                  key={m}
                  onPress={() => setMethod(m)}
                  style={{
                    flexDirection: 'row', alignItems: 'center',
                    backgroundColor: selected ? `${colors.accentBlue}18` : colors.bgCard,
                    borderRadius: 12, padding: 14, marginBottom: 10,
                    borderWidth: 1, borderColor: selected ? colors.accentBlue : colors.borderSubtle,
                  }}
                >
                  <Text style={{ fontSize: 22, marginRight: 12 }}>{cfg.icon}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 15, fontWeight: '600', color: colors.textPrimary }}>{cfg.label}</Text>
                    <Text style={{ fontSize: 12, color: colors.textMuted }}>{cfg.description}</Text>
                  </View>
                  <View style={{
                    width: 18, height: 18, borderRadius: 9, borderWidth: 2,
                    borderColor: selected ? colors.accentBlue : colors.borderSubtle,
                    backgroundColor: selected ? colors.accentBlue : 'transparent',
                  }} />
                </TouchableOpacity>
              );
            })}
          </>
        )}

        {/* Card form */}
        {(method === 'credit_card' || method === 'debit_card') && (
          <View style={{ backgroundColor: colors.bgCard, borderRadius: 14, padding: 16, marginTop: 8, marginBottom: 8, borderWidth: 1, borderColor: colors.borderSubtle }}>
            <Text style={{ fontSize: 15, fontWeight: '600', color: colors.textSecondary, marginBottom: 10 }}>Dados do cartão</Text>
            <TextInput style={inp} placeholder="Nome no cartão" placeholderTextColor={colors.textMuted} value={cardName} onChangeText={setCardName} autoCapitalize="characters" />
            <TextInput style={inp} placeholder="Número do cartão" placeholderTextColor={colors.textMuted} value={cardNumber} onChangeText={(v) => setCardNumber(formatCardNumber(v))} keyboardType="numeric" maxLength={19} />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TextInput style={[inp, { flex: 1 }]} placeholder="Validade (MM/AA)" placeholderTextColor={colors.textMuted} value={expiry} onChangeText={(v) => setExpiry(formatExpiry(v))} keyboardType="numeric" maxLength={5} />
              <TextInput style={[inp, { flex: 1 }]} placeholder="CVV" placeholderTextColor={colors.textMuted} value={ccv} onChangeText={(v) => setCcv(v.replace(/\D/g, '').slice(0, 4))} keyboardType="numeric" maxLength={4} secureTextEntry contextMenuHidden selectTextOnFocus={false} />
            </View>
            <Text style={{ fontSize: 15, fontWeight: '600', color: colors.textSecondary, marginBottom: 10, marginTop: 4 }}>Dados do titular</Text>
            <TextInput style={inp} placeholder="CPF (somente números)" placeholderTextColor={colors.textMuted} value={cpf} onChangeText={(v) => setCpf(v.replace(/\D/g, '').slice(0, 11))} keyboardType="numeric" maxLength={11} />
            <TextInput style={inp} placeholder="CEP (somente números)" placeholderTextColor={colors.textMuted} value={cep} onChangeText={(v) => setCep(v.replace(/\D/g, '').slice(0, 8))} keyboardType="numeric" maxLength={8} />
          </View>
        )}

        <Text style={{ fontSize: 11, color: colors.textMuted, textAlign: 'center', marginTop: 12, marginBottom: 20, lineHeight: 16 }}>
          Ao confirmar, você concorda com os Termos de Uso. Você pode cancelar a qualquer momento.
        </Text>

        <TouchableOpacity
          style={{ backgroundColor: colors.accentBlue, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginBottom: 12 }}
          onPress={handleConfirm}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator color="#FFF" />
            : <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 16 }}>Confirmar assinatura</Text>
          }
        </TouchableOpacity>

        <TouchableOpacity style={{ alignItems: 'center' }} onPress={() => navigation.goBack()}>
          <Text style={{ color: colors.textMuted, fontSize: 14 }}>Voltar</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
