import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  BackHandler,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { WebView, WebViewNavigation } from 'react-native-webview';
import type { WebViewErrorEvent, ShouldStartLoadRequest } from 'react-native-webview/lib/WebViewTypes';

// URL do app web — fonte única da experiência. Cai no domínio canônico se a env não existir.
// Obs.: o apex (tenfy.com.br) é quem serve o app; o subdomínio www não tem cert válido.
const WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL || 'https://tenfy.com.br').trim();
// Host considerado "interno" (navega dentro da WebView). Demais abrem no navegador do sistema.
const APP_HOST = 'tenfy.com.br';

// Cores de marca para o chrome nativo (loading/erro). Espelham o tema do web.
const BG = '#F6F7FA';
const ACCENT = '#0A1330';

export function WebAppShell() {
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);

  // Botão físico de voltar (Android): volta no histórico da WebView quando possível.
  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (canGoBack) {
        webRef.current?.goBack();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [canGoBack]);

  const onNavChange = useCallback((navState: WebViewNavigation) => {
    setCanGoBack(navState.canGoBack);
  }, []);

  // Links externos (outro domínio, mailto, tel, whatsapp) abrem no app nativo correspondente.
  const onShouldStartLoadWithRequest = useCallback((req: ShouldStartLoadRequest): boolean => {
    const url = req.url || '';
    if (/^https?:\/\//i.test(url)) {
      if (!url.toLowerCase().includes(APP_HOST)) {
        Linking.openURL(url).catch(() => {});
        return false;
      }
      return true;
    }
    if (/^(mailto:|tel:|whatsapp:|sms:)/i.test(url)) {
      Linking.openURL(url).catch(() => {});
      return false;
    }
    return true;
  }, []);

  const onError = useCallback((e: WebViewErrorEvent) => {
    // Só tratamos como erro de tela cheia quando o frame principal falha.
    const ne = e.nativeEvent;
    if (ne?.url && !ne.url.toLowerCase().includes(APP_HOST)) return;
    setError(true);
    setLoading(false);
  }, []);

  const reload = useCallback(() => {
    setError(false);
    setLoading(true);
    webRef.current?.reload();
  }, []);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'left', 'right', 'bottom']}>
      {error ? (
        <View style={styles.center}>
          <Text style={styles.errorTitle}>Sem conexão</Text>
          <Text style={styles.errorSubtitle}>
            Não foi possível carregar o Tenfy. Verifique sua internet e tente novamente.
          </Text>
          <TouchableOpacity style={styles.retryButton} onPress={reload} activeOpacity={0.85}>
            <Text style={styles.retryText}>Tentar novamente</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.flex}>
          <WebView
            ref={webRef}
            source={{ uri: WEB_URL }}
            applicationNameForUserAgent="TenfyMobileApp"
            originWhitelist={['*']}
            javaScriptEnabled
            domStorageEnabled
            sharedCookiesEnabled
            thirdPartyCookiesEnabled
            allowsBackForwardNavigationGestures
            pullToRefreshEnabled
            mediaPlaybackRequiresUserAction
            setSupportMultipleWindows={false}
            onLoadStart={() => setLoading(true)}
            onLoadEnd={() => setLoading(false)}
            onError={onError}
            onNavigationStateChange={onNavChange}
            onShouldStartLoadWithRequest={onShouldStartLoadWithRequest}
            style={styles.webview}
          />
          {loading ? (
            <View style={styles.loadingOverlay} pointerEvents="none">
              <ActivityIndicator size="large" color={ACCENT} />
            </View>
          ) : null}
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  flex: { flex: 1 },
  webview: { flex: 1, backgroundColor: BG },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: BG,
  },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28, backgroundColor: BG },
  errorTitle: { fontSize: 20, fontWeight: '700', color: ACCENT, marginBottom: 8, textAlign: 'center' },
  errorSubtitle: { fontSize: 14, color: '#5F738C', textAlign: 'center', lineHeight: 20, marginBottom: 24 },
  retryButton: { backgroundColor: ACCENT, borderRadius: 12, paddingHorizontal: 24, paddingVertical: 12 },
  retryText: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
});
