import React from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppText } from './ui';
import { useTheme } from '../contexts/ThemeContext';
import { useNetworkStatus } from '../hooks/useNetworkStatus';

export function OfflineBanner() {
  const { isOffline } = useNetworkStatus();
  const { colors } = useTheme();
  if (!isOffline) return null;
  return (
    <View style={[styles.banner, { backgroundColor: colors.bgElevated, borderBottomColor: colors.statusCanceled + '44' }]}>
      <Ionicons name="cloud-offline-outline" size={14} color={colors.statusCanceled} />
      <AppText variant="caption" style={{ color: colors.statusCanceled, fontWeight: '600' }}>
        Sem conexão — exibindo dados salvos
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 7,
    paddingHorizontal: 16,
    justifyContent: 'center',
    borderBottomWidth: 1,
  },
});
