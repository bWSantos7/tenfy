import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ErrorBoundary } from './src/components/ErrorBoundary';
import { WebAppShell } from './src/WebAppShell';

/**
 * O app mobile é uma casca nativa que carrega o app web (https://tenfy.com.br)
 * dentro de uma WebView. Assim a experiência fica 100% idêntica ao web — layout,
 * cores, espaçamentos, tipografia, ícones, fluxos, botões, estados e responsividade —
 * porque é literalmente o web rodando. Toda a lógica (auth, navegação, tema, dados)
 * vive no app web; aqui só tratamos o chrome nativo, loading e erro de conexão.
 */
export default function App() {
  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <StatusBar style="auto" />
        <WebAppShell />
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}
