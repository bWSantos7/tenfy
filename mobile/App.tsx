import React from 'react';
import { NavigationContainer, DefaultTheme, DarkTheme } from '@react-navigation/native';
import Toast from 'react-native-toast-message';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from './src/contexts/AuthContext';
import { ThemeProvider, useTheme } from './src/contexts/ThemeContext';
import { RootNavigator } from './src/navigation/RootNavigator';
import { ErrorBoundary } from './src/components/ErrorBoundary';
import { OfflineBanner } from './src/components/OfflineBanner';

function AppContent() {
  const { ready } = useAuth();
  const { theme, colors } = useTheme();
  if (!ready) return null;
  const navTheme = theme === 'dark'
    ? { ...DarkTheme,   colors: { ...DarkTheme.colors,   background: colors.bgBase, card: colors.bgCard, border: colors.borderSubtle, text: colors.textPrimary, primary: colors.accentNeon } }
    : { ...DefaultTheme, colors: { ...DefaultTheme.colors, background: colors.bgBase, card: colors.bgCard, border: colors.borderSubtle, text: colors.textPrimary, primary: colors.accentNeon } };
  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style={theme === 'dark' ? 'light' : 'dark'} />
      <OfflineBanner />
      <RootNavigator />
      <Toast />
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <ErrorBoundary>
            <AppContent />
          </ErrorBoundary>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
