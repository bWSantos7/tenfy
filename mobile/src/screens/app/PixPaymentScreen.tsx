import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  ScrollView,
  Share,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTheme } from '../../contexts/ThemeContext';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { fetchSubscription } from '../../services/billing';

type PixRoute = RouteProp<MainStackParamList, 'PixPayment'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

const POLL_INTERVAL = 5000;

export function PixPaymentScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<PixRoute>();
  const { pixData } = route.params;
  const { colors } = useTheme();

  const [checking, setChecking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [paymentState, setPaymentState] = useState<'waiting' | 'confirmed' | 'expired' | 'error'>('waiting');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;

    pollRef.current = setInterval(async () => {
      if (!mounted) return;
      try {
        const sub = await fetchSubscription();
        if (mounted && sub.status === 'active') {
          setPaymentState('confirmed');
          clearInterval(pollRef.current!);
          Alert.alert('Pagamento confirmado!', 'Sua assinatura está ativa.', [
            { text: 'OK', onPress: () => { if (mounted) navigation.replace('Subscription'); } },
          ]);
        }
      } catch {
        if (mounted) setPaymentState('error');
      }
    }, POLL_INTERVAL);

    return () => {
      mounted = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (!pixData.expiration) return;
    const expiresAt = new Date(pixData.expiration).getTime();
    if (Number.isFinite(expiresAt) && expiresAt < Date.now()) {
      setPaymentState('expired');
    }
  }, [pixData.expiration]);

  async function handleCopy() {
    await Share.share({ message: pixData.copia_e_cola });
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  }

  async function handleCheckManually() {
    setChecking(true);
    try {
      const sub = await fetchSubscription();
      if (sub.status === 'active') {
        setPaymentState('confirmed');
        navigation.replace('Subscription');
      } else {
        setPaymentState('waiting');
        Alert.alert('Pagamento pendente', 'Ainda não identificamos seu pagamento. Aguarde alguns instantes.');
      }
    } catch {
      setPaymentState('error');
      Alert.alert('Erro', 'Não foi possível verificar o pagamento.');
    } finally {
      setChecking(false);
    }
  }

  const stateBadgeStyle = {
    confirmed: { bg: `${colors.accentNeon}15`, border: `${colors.accentNeon}50`, text: colors.accentNeon },
    expired:   { bg: '#ef444415', border: '#ef444450', text: '#ef4444' },
    error:     { bg: '#ef444415', border: '#ef444450', text: '#ef4444' },
    waiting:   { bg: `${colors.accentBlue}15`, border: `${colors.accentBlue}50`, text: colors.accentBlue },
  };
  const bState = paymentState === 'confirmed' ? stateBadgeStyle.confirmed
    : (paymentState === 'expired' || paymentState === 'error') ? stateBadgeStyle.expired
    : stateBadgeStyle.waiting;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bgBase }}
      contentContainerStyle={{ padding: 24, paddingBottom: 40, alignItems: 'center' }}
    >
      <Text style={{ fontSize: 22, fontWeight: '700', color: colors.textPrimary, marginBottom: 8, textAlign: 'center' }}>
        Pague com Pix
      </Text>
      <Text style={{ fontSize: 14, color: colors.textMuted, textAlign: 'center', lineHeight: 20, marginBottom: 24 }}>
        Escaneie o QR code ou copie o código abaixo no seu banco. A confirmação é automática em até 1 minuto.
      </Text>

      {/* State badge */}
      <View style={{ borderRadius: 999, paddingHorizontal: 14, paddingVertical: 7, marginBottom: 18, borderWidth: 1, backgroundColor: bState.bg, borderColor: bState.border }}>
        <Text style={{ fontSize: 12, fontWeight: '700', color: bState.text }}>
          {paymentState === 'confirmed' ? 'Pagamento confirmado'
            : paymentState === 'expired' ? 'Pix expirado'
            : paymentState === 'error' ? 'Erro ao verificar pagamento'
            : 'Aguardando pagamento'}
        </Text>
      </View>

      {/* QR Code */}
      {pixData.qr_code_image ? (
        <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, padding: 16, marginBottom: 24, borderWidth: 1, borderColor: colors.borderSubtle }}>
          {pixData.qr_code_image.startsWith('iVBOR') ? (
            <Image source={{ uri: `data:image/png;base64,${pixData.qr_code_image}` }} style={{ width: 220, height: 220 }} resizeMode="contain" />
          ) : (
            <Text style={{ color: '#ef4444', textAlign: 'center' }}>QR code inválido. Use o código Copia e Cola.</Text>
          )}
        </View>
      ) : (
        <View style={{ width: 220, height: 220, justifyContent: 'center', alignItems: 'center', marginBottom: 24 }}>
          <ActivityIndicator size="large" color={colors.accentBlue} />
          <Text style={{ marginTop: 12, color: colors.textMuted, fontSize: 14 }}>Gerando QR code...</Text>
        </View>
      )}

      {/* Copia e cola */}
      {pixData.copia_e_cola ? (
        <View style={{ width: '100%', backgroundColor: colors.bgCard, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.borderSubtle }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: colors.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Pix Copia e Cola</Text>
          <Text numberOfLines={3} ellipsizeMode="middle" style={{ fontSize: 12, color: colors.textSecondary, fontFamily: 'monospace', marginBottom: 12, lineHeight: 18 }}>
            {pixData.copia_e_cola}
          </Text>
          <TouchableOpacity onPress={handleCopy} style={{ backgroundColor: `${colors.accentBlue}18`, borderRadius: 8, paddingVertical: 10, alignItems: 'center' }}>
            <Text style={{ color: colors.accentBlue, fontWeight: '600', fontSize: 14 }}>
              {copied ? 'Código aberto para copiar' : 'Copiar código Pix'}
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {pixData.expiration ? (
        <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 24 }}>
          Válido até: {new Date(pixData.expiration).toLocaleString('pt-BR')}
        </Text>
      ) : null}

      {paymentState !== 'expired' ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 20 }}>
          <ActivityIndicator size="small" color={colors.accentBlue} style={{ marginRight: 8 }} />
          <Text style={{ fontSize: 13, color: colors.textMuted }}>Verificando pagamento automaticamente...</Text>
        </View>
      ) : null}

      <TouchableOpacity
        style={{ width: '100%', backgroundColor: colors.accentBlue, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginBottom: 12 }}
        onPress={handleCheckManually}
        disabled={checking}
      >
        {checking
          ? <ActivityIndicator color="#FFF" />
          : <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 15 }}>Já paguei — verificar agora</Text>
        }
      </TouchableOpacity>

      <TouchableOpacity style={{ paddingVertical: 8 }} onPress={() => navigation.navigate('Subscription')}>
        <Text style={{ color: colors.textMuted, fontSize: 14 }}>Pagar depois</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}
