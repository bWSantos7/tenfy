import React, { useState } from 'react';
import { Image, Pressable, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AuthStackParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { login } from '../../services/auth';
import { extractApiError } from '../../services/api';
import { AppText, Button, Card, Input, Screen } from '../../components/ui';

type Props = NativeStackScreenProps<AuthStackParamList, 'Login'>;

export function LoginScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!email.trim() || !password) {
      Toast.show({
        type: 'error',
        text1: 'Preencha e-mail e senha',
        text2: 'Os dois campos são obrigatórios para entrar.',
      });
      return;
    }
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      setUser(data.user);
      Toast.show({ type: 'success', text1: 'Bem-vindo de volta!' });
    } catch (err) {
      const message = extractApiError(err);
      console.warn('Login failed:', message);
      Toast.show({ type: 'error', text1: 'Erro ao entrar', text2: message, visibilityTime: 6000 });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen scroll={false}>
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <View style={{ alignItems: 'center', marginBottom: 24 }}>
          <View style={{ width: 72, height: 72, borderRadius: 20, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <Image source={require('../../../assets/icon.png')} style={{ width: 52, height: 52 }} resizeMode="contain" tintColor={colors.bgBase} />
          </View>
          <AppText variant="title">Tennis Hub</AppText>
          <AppText variant="muted" style={{ marginTop: 6 }}>Seu hub de torneios de tênis</AppText>
        </View>
        <Card>
          <Input label="E-mail" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="voce@exemplo.com" />
          <Input label="Senha" value={password} onChangeText={setPassword} secureTextEntry placeholder="••••••••" />
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
