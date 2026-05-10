import React from 'react';
import { Modal, View, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppText, Button } from './ui';
import { useTheme } from '../contexts/ThemeContext';

type Props = {
  visible: boolean;
  onClose: () => void;
};

export function BetaModal({ visible, onClose }: Props) {
  const { colors } = useTheme();

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      statusBarTranslucent
    >
      <View style={styles.overlay}>
        <View style={[styles.card, { backgroundColor: colors.bgCard, borderColor: colors.borderSubtle }]}>
          <View style={[
            styles.iconWrap,
            { backgroundColor: `${colors.accentNeon}18`, borderColor: `${colors.accentNeon}44` },
          ]}>
            <Ionicons name="flask-outline" size={32} color={colors.accentNeon} />
          </View>

          <AppText variant="title" style={{ textAlign: 'center', marginBottom: 8 }}>
            Versão Beta
          </AppText>

          <AppText variant="body" style={{ textAlign: 'center', color: colors.textSecondary, lineHeight: 22, marginBottom: 24 }}>
            Você está acessando uma versão beta do Tenfy (MVP). O app ainda está em testes e pode conter erros ou instabilidades.{'\n\n'}
            Neste período, a criação de conta é gratuita e todas as funcionalidades disponíveis estão liberadas.
          </AppText>

          <Button title="Entendi" onPress={onClose} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  card: {
    width: '100%',
    borderRadius: 20,
    borderWidth: 1,
    padding: 28,
    alignItems: 'center',
  },
  iconWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
});
