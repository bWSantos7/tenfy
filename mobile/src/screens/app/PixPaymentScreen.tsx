import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Share,
  Text,
  View,
} from 'react-native';
import { useTheme } from '../../contexts/ThemeContext';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList } from '../../navigation/types';
import { fetchSubscription } from '../../services/billing';
import { Screen, AppText, Card, Button } from '../../components/ui';

type PixRoute = RouteProp<MainStackParamList, 'PixPayment'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

const POLL_INTERVAL = 5000;

export function PixPaymentScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<PixRoute>();
  const { pixData } = route.params;
  const { colors } = useTheme();

  const { refresh: refreshAuth } = useAuth();
  const [checking, setChecking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [paymentState, setPaymentState] = useState<'waiting' | 'confirmed' | 'expired' | 'error'>('waiting');
  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  // Guard against concurrent polling requests (prevents overlapping async calls)
  const isPolling  = useRef(false);

  useEffect(() => {
    let mounted = true;

    pollRef.current = setInterval(async () => {
      if (!mounted || isPolling.current) return;
      isPolling.current = true;
      try {
        const sub = await fetchSubscription();
        if (!mounted) return;
        if (sub?.status === 'active') {
          setPaymentState('confirmed');
          clearInterval(pollRef.current!);
          // Refresh AuthContext so subscriptionStatus updates → GatedTabs sees 'active'
          await refreshAuth().catch(() => {});
          Alert.alert('Pagamento confirmado!', 'Sua assinatura está ativa.', [
            { text: 'OK', onPress: () => { if (mounted) navigation.replace('Subscription'); } },
          ]);
        }
      } catch {
        // Network error — stop polling to avoid hammering the server
        if (mounted) {
          setPaymentState('error');
          clearInterval(pollRef.current!);
        }
      } finally {
        isPolling.current = false;
      }
    }, POLL_INTERVAL);

    return () => {
      mounted = false;
      isPolling.current = false;
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
      if (sub?.status === 'active') {
        setPaymentState('confirmed');
        await refreshAuth().catch(() => {});
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

  const stateBadge = {
    confirmed: { bg: `${colors.accentNeon}15`, border: `${colors.accentNeon}50`, text: colors.accentNeon },
    expired:   { bg: `${colors.danger}15`, border: `${colors.danger}50`, text: colors.danger },
    error:     { bg: `${colors.danger}15`, border: `${colors.danger}50`, text: colors.danger },
    waiting:   { bg: `${colors.accentBlue}15`, border: `${colors.accentBlue}50`, text: colors.accentBlue },
  };
  const badge = paymentState === 'confirmed' ? stateBadge.confirmed
    : (paymentState === 'expired' || paymentState === 'error') ? stateBadge.expired
    : stateBadge.waiting;

  const badgeLabel = paymentState === 'confirmed' ? 'Pagamento confirmado'
    : paymentState === 'expired' ? 'Pix expirado'
    : paymentState === 'error' ? 'Erro ao verificar pagamento'
    : 'Aguardando pagamento';

  return (
    <Screen>
      <AppText variant="title" style={{ textAlign: 'center', marginBottom: 8 }}>
        Pague com Pix
      </AppText>
      <AppText variant="muted" style={{ textAlign: 'center', lineHeight: 20, marginBottom: 24 }}>
        Escaneie o QR code ou copie o código abaixo no seu banco. A confirmação é automática em até 1 minuto.
      </AppText>

      {/* Status badge */}
      <View style={{
        alignSelf: 'center', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 7,
        marginBottom: 18, borderWidth: 1, backgroundColor: badge.bg, borderColor: badge.border,
      }}>
        <AppText style={{ fontSize: 12, fontWeight: '700', color: badge.text }}>
          {badgeLabel}
        </AppText>
      </View>

      {/* QR Code */}
      {pixData.qr_code_image ? (
        <Card style={{ alignItems: 'center', marginBottom: 24 }}>
          {pixData.qr_code_image.startsWith('iVBOR') ? (
            <Image
              source={{ uri: `data:image/png;base64,${pixData.qr_code_image}` }}
              style={{ width: 220, height: 220 }}
              resizeMode="contain"
            />
          ) : (
            <AppText style={{ color: colors.danger, textAlign: 'center' }}>
              QR code inválido. Use o código Copia e Cola.
            </AppText>
          )}
        </Card>
      ) : (
        <View style={{ alignSelf: 'center', width: 220, height: 220, justifyContent: 'center', alignItems: 'center', marginBottom: 24 }}>
          <ActivityIndicator size="large" color={colors.accentBlue} />
          <AppText variant="muted" style={{ marginTop: 12 }}>Gerando QR code...</AppText>
        </View>
      )}

      {/* Copia e cola */}
      {pixData.copia_e_cola ? (
        <Card style={{ marginBottom: 16 }}>
          <AppText
            variant="caption"
            style={{ fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}
          >
            Pix Copia e Cola
          </AppText>
          <Text
            numberOfLines={3}
            ellipsizeMode="middle"
            style={{ fontSize: 12, color: colors.textSecondary, fontFamily: 'monospace', marginBottom: 12, lineHeight: 18 }}
          >
            {pixData.copia_e_cola}
          </Text>
          <Button
            title={copied ? 'Código aberto para copiar' : 'Copiar código Pix'}
            onPress={handleCopy}
            variant="secondary"
          />
        </Card>
      ) : null}

      {pixData.expiration ? (
        <AppText variant="caption" style={{ marginBottom: 24, textAlign: 'center' }}>
          Válido até: {new Date(pixData.expiration).toLocaleString('pt-BR')}
        </AppText>
      ) : null}

      {paymentState !== 'expired' ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
          <ActivityIndicator size="small" color={colors.accentBlue} style={{ marginRight: 8 }} />
          <AppText variant="muted">Verificando pagamento automaticamente...</AppText>
        </View>
      ) : null}

      <Button
        title="Já paguei — verificar agora"
        onPress={handleCheckManually}
        loading={checking}
        style={{ marginBottom: 12 }}
      />

      <Button
        title="Pagar depois"
        onPress={() => navigation.navigate('Subscription')}
        variant="ghost"
      />
    </Screen>
  );
}
