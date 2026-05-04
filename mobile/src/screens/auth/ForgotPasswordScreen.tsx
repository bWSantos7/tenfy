import React, { useState } from 'react';
import { View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AuthStackParamList } from '../../navigation/types';
import { AppText, Button, Card, Input, Screen } from '../../components/ui';
import api from '../../services/api';

type Props = NativeStackScreenProps<AuthStackParamList, 'ForgotPassword'>;

export function ForgotPasswordScreen({ navigation }: Props) {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit() {
    setSubmitting(true);
    try { await api.post('/api/auth/password-reset/', { email: email.trim().toLowerCase() }); } catch {}
    finally {
      setSent(true);
      setSubmitting(false);
      Toast.show({ type: 'success', text1: 'Se o e-mail existir, enviaremos as instruções.' });
    }
  }

  return (
    <Screen scroll={false}>
      <View style={{ flex: 1, justifyContent: 'center' }}>
        {sent ? (
          <Card>
            <AppText variant="section">Verifique seu e-mail</AppText>
            <AppText variant="body">Se {email} estiver cadastrado, você receberá as instruções em instantes.</AppText>
            <Button title="Voltar ao login" onPress={() => navigation.navigate('Login')} />
          </Card>
        ) : (
          <Card>
            <AppText variant="section">Recuperar senha</AppText>
            <Input label="E-mail" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="voce@exemplo.com" />
            <Button title="Enviar instruções" onPress={onSubmit} loading={submitting} />
            <Button title="Voltar" variant="ghost" onPress={() => navigation.goBack()} />
          </Card>
        )}
      </View>
    </Screen>
  );
}
