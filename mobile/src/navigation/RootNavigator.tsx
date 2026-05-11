import React, { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { AppText, Button } from '../components/ui';
import { AuthStackParamList, MainStackParamList } from './types';
import { BetaModal } from '../components/BetaModal';
import { storage } from '../services/api';

const BETA_ACK_KEY = 'th_beta_ack';
import { LoginScreen } from '../screens/auth/LoginScreen';
import { RegisterScreen } from '../screens/auth/RegisterScreen';
import { ForgotPasswordScreen } from '../screens/auth/ForgotPasswordScreen';
import { MainTabs } from './Tabs';
import { TournamentDetailScreen } from '../screens/app/TournamentDetailScreen';
import { OnboardingScreen } from '../screens/app/OnboardingScreen';
import { CoachScreen } from '../screens/app/CoachScreen';
import { AdminPanelScreen } from '../screens/app/AdminPanelScreen';
import { MyRegistrationsScreen } from '../screens/app/MyRegistrationsScreen';
import { RegistrationListScreen } from '../screens/app/RegistrationListScreen';
import { PlansScreen } from '../screens/app/PlansScreen';
import { CheckoutScreen } from '../screens/app/CheckoutScreen';
import { PixPaymentScreen } from '../screens/app/PixPaymentScreen';
import { SubscriptionScreen } from '../screens/app/SubscriptionScreen';
import { TournamentCompareScreen } from '../screens/app/TournamentCompareScreen';

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const MainStack = createNativeStackNavigator<MainStackParamList>();

/**
 * GatedTabs replaces MainTabs as the root "Tabs" screen.
 *
 * Payment gate: if the user chose a paid plan but payment is not yet confirmed
 * (subscriptionStatus === 'pending'), we block access to the normal tabs and
 * redirect to the payment flow. Once the webhook fires and subscription becomes
 * 'active', AuthContext.refresh() updates subscriptionStatus and tabs unlock.
 *
 * Free users (no subscription → subscriptionStatus === 'none') always pass through.
 */
function GatedTabs() {
  const { subscriptionStatus, logout } = useAuth();
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<MainStackParamList>>();

  if (subscriptionStatus === 'pending') {
    return (
      <SafeAreaView
        style={{ flex: 1, backgroundColor: colors.bgBase }}
        edges={['top', 'left', 'right', 'bottom']}
      >
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 28 }}>
          <View style={{
            width: 80, height: 80, borderRadius: 40,
            backgroundColor: `${colors.accentNeon}18`,
            borderWidth: 2, borderColor: `${colors.accentNeon}44`,
            alignItems: 'center', justifyContent: 'center', marginBottom: 24,
          }}>
            <Ionicons name="card-outline" size={36} color={colors.accentNeon} />
          </View>

          <AppText variant="title" style={{ textAlign: 'center', marginBottom: 8 }}>
            Pagamento pendente
          </AppText>
          <AppText variant="muted" style={{ textAlign: 'center', lineHeight: 22, marginBottom: 32 }}>
            Seu plano foi selecionado, mas o pagamento ainda não foi confirmado.
            Conclua o pagamento para ativar sua assinatura e acessar todos os recursos.
          </AppText>

          <View style={{ width: '100%', gap: 12 }}>
            <Button
              title="Ir para pagamento"
              onPress={() => navigation.navigate('Plans')}
            />
            <Button
              title="Minha assinatura"
              variant="secondary"
              onPress={() => navigation.navigate('Subscription')}
            />
          </View>

          <Pressable onPress={logout} style={{ marginTop: 24, padding: 8 }}>
            <AppText variant="caption" style={{ color: colors.textMuted, textDecorationLine: 'underline' }}>
              Sair da conta
            </AppText>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return <MainTabs />;
}

export function RootNavigator() {
  const { isAuthenticated } = useAuth();
  const [betaVisible, setBetaVisible] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    Promise.all([
      storage.get(BETA_ACK_KEY),
      storage.get('th_just_registered'),
    ]).then(([acked, justReg]) => {
      if (!acked || justReg) {
        storage.delete('th_just_registered');
        setBetaVisible(true);
      }
    });
  }, [isAuthenticated]);

  const dismissBeta = async () => {
    await storage.set(BETA_ACK_KEY, '1');
    setBetaVisible(false);
  };

  if (!isAuthenticated) {
    return (
      <AuthStack.Navigator screenOptions={{ headerShown: false }}>
        <AuthStack.Screen name="Login" component={LoginScreen} />
        <AuthStack.Screen name="Register" component={RegisterScreen} />
        <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
      </AuthStack.Navigator>
    );
  }

  return (
    <>
      <BetaModal visible={betaVisible} onClose={dismissBeta} />
      <MainStack.Navigator screenOptions={{ headerShown: false }}>
      <MainStack.Screen name="Tabs" component={GatedTabs} />
      <MainStack.Screen name="TournamentDetail" component={TournamentDetailScreen} />
      <MainStack.Screen name="Onboarding" component={OnboardingScreen} />
      <MainStack.Screen name="Coach" component={CoachScreen} />
      <MainStack.Screen name="AdminPanel" component={AdminPanelScreen} />
      <MainStack.Screen name="MyRegistrations" component={MyRegistrationsScreen} />
      <MainStack.Screen name="RegistrationList" component={RegistrationListScreen} />
      <MainStack.Screen
        name="Plans"
        component={PlansScreen}
        options={{ headerShown: true, title: 'Escolha seu plano', headerBackTitle: 'Voltar' }}
      />
      <MainStack.Screen
        name="Checkout"
        component={CheckoutScreen}
        options={{ headerShown: true, title: 'Finalizar assinatura', headerBackTitle: 'Voltar' }}
      />
      <MainStack.Screen
        name="PixPayment"
        component={PixPaymentScreen}
        options={{ headerShown: true, title: 'Pagamento Pix', headerBackTitle: 'Voltar' }}
      />
      <MainStack.Screen
        name="Subscription"
        component={SubscriptionScreen}
        options={{ headerShown: true, title: 'Minha assinatura', headerBackTitle: 'Voltar' }}
      />
      <MainStack.Screen
        name="TournamentCompare"
        component={TournamentCompareScreen}
        options={{ headerShown: true, title: 'Comparar torneios', headerBackTitle: 'Voltar' }}
      />
    </MainStack.Navigator>
    </>
  );
}
