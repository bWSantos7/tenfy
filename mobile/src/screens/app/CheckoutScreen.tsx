import React, { useState } from 'react';
import { Alert, TouchableOpacity, View } from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { checkout, CheckoutPayload } from '../../services/billing';
import { tokenizeCard, getAsaasCustomerId } from '../../services/asaas';
import api, { extractApiError } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { Screen, AppText, Card, Button, Input } from '../../components/ui';

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
  const [cardName, setCardName]     = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry]         = useState('');
  const [ccv, setCcv]               = useState('');
  const [cpf, setCpf]               = useState('');
  const [cep, setCep]               = useState('');

  const price = billingPeriod === 'yearly' ? plan.price_yearly : plan.price_monthly;

  function validateCard(): string | null {
    if (!cardName.trim())                          return 'Informe o nome no cartão.';
    if (cardNumber.replace(/\s/g, '').length < 16) return 'Número do cartão inválido.';
    if (expiry.length < 5)                         return 'Informe a validade (MM/AA).';
    if (ccv.length < 3)                            return 'CVV inválido.';
    if (cpf.replace(/\D/g, '').length < 11)        return 'CPF inválido.';
    if (cep.replace(/\D/g, '').length < 8)         return 'CEP inválido.';
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
        } catch {
          Alert.alert('Erro no cartão', 'Dados do cartão inválidos. Verifique e tente novamente.');
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
      const msg = err?.response?.status === 402
        ? 'Pagamento recusado. Verifique os dados do cartão ou escolha outro método.'
        : extractApiError(err);
      Alert.alert('Erro no pagamento', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen>
      <AppText variant="title">Finalizar assinatura</AppText>

      {/* Summary */}
      <View style={{ backgroundColor: colors.accentBlue, borderRadius: 14, padding: 20 }}>
        <AppText variant="caption" style={{ color: 'rgba(255,255,255,0.8)', marginBottom: 4 }}>
          {plan.name}
        </AppText>
        <AppText variant="title" style={{ color: '#FFF', fontSize: 26, fontWeight: '800' }}>
          {formatPrice(price, billingPeriod)}
        </AppText>
        {billingPeriod === 'yearly' && (
          <AppText variant="caption" style={{ color: 'rgba(255,255,255,0.7)', marginTop: 6 }}>
            Equivale a R$ {(parseFloat(price) / 12).toFixed(2).replace('.', ',')}/mês — 2 meses grátis
          </AppText>
        )}
      </View>

      {/* Payment method */}
      <View style={{ gap: 8 }}>
        <AppText variant="muted" style={{ fontWeight: '600' }}>Forma de pagamento</AppText>
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
                borderRadius: 12, padding: 14,
                borderWidth: 1, borderColor: selected ? colors.accentBlue : colors.borderSubtle,
              }}
            >
              <AppText style={{ fontSize: 22, marginRight: 12 }}>{cfg.icon}</AppText>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontWeight: '600' }}>{cfg.label}</AppText>
                <AppText variant="caption">{cfg.description}</AppText>
              </View>
              <View style={{
                width: 18, height: 18, borderRadius: 9, borderWidth: 2,
                borderColor: selected ? colors.accentBlue : colors.borderSubtle,
                backgroundColor: selected ? colors.accentBlue : 'transparent',
              }} />
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Card form */}
      {(method === 'credit_card' || method === 'debit_card') && (
        <Card>
          <AppText variant="caption" style={{ fontWeight: '600' }}>Dados do cartão</AppText>
          <Input
            placeholder="Nome no cartão"
            value={cardName}
            onChangeText={setCardName}
            autoCapitalize="characters"
          />
          <Input
            placeholder="Número do cartão"
            value={cardNumber}
            onChangeText={(v) => setCardNumber(formatCardNumber(v))}
            keyboardType="numeric"
            maxLength={19}
          />
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Input
                placeholder="Validade (MM/AA)"
                value={expiry}
                onChangeText={(v) => setExpiry(formatExpiry(v))}
                keyboardType="numeric"
                maxLength={5}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Input
                placeholder="CVV"
                value={ccv}
                onChangeText={(v) => setCcv(v.replace(/\D/g, '').slice(0, 4))}
                keyboardType="numeric"
                maxLength={4}
                secureTextEntry
                contextMenuHidden
                selectTextOnFocus={false}
              />
            </View>
          </View>
          <AppText variant="caption" style={{ fontWeight: '600', marginTop: 4 }}>Dados do titular</AppText>
          <Input
            placeholder="CPF (somente números)"
            value={cpf}
            onChangeText={(v) => setCpf(v.replace(/\D/g, '').slice(0, 11))}
            keyboardType="numeric"
            maxLength={11}
          />
          <Input
            placeholder="CEP (somente números)"
            value={cep}
            onChangeText={(v) => setCep(v.replace(/\D/g, '').slice(0, 8))}
            keyboardType="numeric"
            maxLength={8}
          />
        </Card>
      )}

      <AppText variant="caption" style={{ textAlign: 'center', lineHeight: 16 }}>
        Ao confirmar, você concorda com os Termos de Uso. Você pode cancelar a qualquer momento.
      </AppText>

      <Button title="Confirmar assinatura" onPress={handleConfirm} loading={loading} />
      <Button title="Voltar" variant="ghost" onPress={() => navigation.goBack()} />
    </Screen>
  );
}
