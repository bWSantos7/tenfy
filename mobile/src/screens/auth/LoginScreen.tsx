import React, { useState } from 'react';
import { Image, Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { AuthStackParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { login } from '../../services/auth';
import { AppText, Button, Card, Input, Screen } from '../../components/ui';

type Props = NativeStackScreenProps<AuthStackParamList, 'Login'>;

export function LoginScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function onSubmit() {
    setLoginError(null);
    if (!email.trim() || !password) {
      setLoginError('Preencha e-mail e senha para continuar.');
      return;
    }
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      setUser(data.user);
      Toast.show({ type: 'success', text1: 'Bem-vindo de volta!' });
    } catch {
      setLoginError('E-mail ou senha incorretos. Verifique os dados ou redefina sua senha.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen scroll={false}>
      <View style={{ flex: 1, justifyContent: 'center', paddingHorizontal: 16 }}>
        <View style={{ alignItems: 'center', marginBottom: 32 }}>
          <Image
            source={require('../../../assets/logo2.png')}
            style={{ width: 220, height: 70 }}
            resizeMode="contain"
          />
        </View>
        <Card>
          <Input label="E-mail" value={email} onChangeText={(v) => { setLoginError(null); setEmail(v); }} autoCapitalize="none" keyboardType="email-address" placeholder="voce@exemplo.com" />
          <Input label="Senha" value={password} onChangeText={(v) => { setLoginError(null); setPassword(v); }} secureTextEntry placeholder="••••••••" />
          {loginError ? (
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: `${colors.danger}18`, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: `${colors.danger}44` }}>
              <Ionicons name="alert-circle-outline" size={16} color={colors.danger} style={{ marginTop: 1 }} />
              <AppText variant="caption" style={{ flex: 1, color: colors.danger, lineHeight: 18 }}>{loginError}</AppText>
            </View>
          ) : null}
          <Button title="Entrar" onPress={onSubmit} loading={submitting} />
          <Pressable onPress={() => navigation.navigate('ForgotPassword')} style={{ alignItems: 'center' }}>
            <AppText variant="caption">Esqueceu a senha?</AppText>
          </Pressable>
        </Card>
        <View style={{ alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 4, marginTop: 16 }}>
          <AppText variant="body" style={{ color: colors.textSecondary }}>Novo por aqui?</AppText>
          <Pressable onPress={() => navigation.navigate('Register')}>
            <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '600' }}>Criar conta</AppText>
          </Pressable>
        </View>
      </View>
    </Screen>
  );
}
