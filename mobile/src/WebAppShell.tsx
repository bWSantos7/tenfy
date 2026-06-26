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
import * as Notifications from 'expo-notifications';
import { registerForPushToken, PushToken } from './push';

// URL do app web — fonte única da experiência. Cai no domínio canônico se a env não existir.
// Obs.: o apex (tenfy.com.br) é quem serve o app; o subdomínio www não tem cert válido.
const WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL || 'https://tenfy.com.br').trim();
// Host considerado "interno" (navega dentro da WebView). Demais abrem no navegador do sistema.
const APP_HOST = 'tenfy.com.br';
// Caminho inicial do app: abre direto no login. Quem já está logado é redirecionado
// para /inicio pelo próprio web (PublicOnlyRoute), então não trava o usuário autenticado.
const INITIAL_URL = `${WEB_URL.replace(/\/+$/, '')}/login`;

// Cores de marca para o chrome nativo (loading/erro). Espelham o tema do web.
const BG = '#F6F7FA';
const ACCENT = '#0A1330';

// Sinaliza ao app web em qual sistema a casca está rodando. No iOS, o web usa isso
// para ocultar cadastro/checkout e operar apenas com login (conformidade Apple 3.1.1).
// Roda antes do conteúdo carregar; a UA "TenfyMobileApp" é o fallback do lado web.
const INJECT_PLATFORM = `(function(){try{window.__TENFY_APP_OS__=${JSON.stringify(
  Platform.OS,
)};window.__TENFY_MOBILE_APP__=true;}catch(e){}})();true;`;

// Entrega o push token ao app web, que o associa ao usuário logado (tem o JWT) via
// POST /api/alerts/register-device/. Reinjetado a cada carregamento (o web reseta a var).
const pushTokenJS = (t: PushToken) =>
  `(function(){try{window.__TENFY_PUSH_TOKEN__=${JSON.stringify(
    t,
  )};window.dispatchEvent(new Event('tenfy-push-token'));}catch(e){}})();true;`;

export function WebAppShell() {
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);
  // URL carregada na WebView. Começa no login e muda quando um universal link de retorno
  // (ex.: /app/continuar?ht=...) abre o app — aí navegamos a WebView para esse link, que
  // troca o token por sessão e entra logado (retorno automático após assinar no site).
  const [currentUri, setCurrentUri] = useState(INITIAL_URL);
  // O overlay nativo de loading só faz sentido no primeiro carregamento do documento.
  // Navegações internas do app (SPA / pushState, ex.: login -> /inicio) podem disparar
  // onLoadStart sem um onLoadEnd correspondente no Android, deixando o spinner preso.
  // Após o primeiro carregamento, o próprio web cuida dos estados de loading.
  const hasLoadedOnce = useRef(false);
  // Push token nativo, guardado em ref para reinjetar a cada carregamento da WebView.
  const pushTokenRef = useRef<PushToken | null>(null);

  // Push nativo: pede permissão, obtém o token e o injeta na WebView (que o registra no
  // backend com o JWT). Também navega para a tela certa quando o usuário toca na notificação.
  useEffect(() => {
    let mounted = true;
    registerForPushToken().then((t) => {
      if (!mounted || !t) return;
      pushTokenRef.current = t;
      webRef.current?.injectJavaScript(pushTokenJS(t));
    });
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      const path = response.notification.request.content.data?.path;
      if (typeof path === 'string' && path.startsWith('/')) {
        hasLoadedOnce.current = false;
        setError(false);
        setLoading(true);
        setCurrentUri(`${WEB_URL.replace(/\/+$/, '')}${path}`);
      }
    });
    return () => { mounted = false; sub.remove(); };
  }, []);

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

  // Deep links / universal links (https://tenfy.com.br/app/...): carrega o destino na
  // WebView, tanto no cold start (app fechado) quanto com o app já aberto.
  useEffect(() => {
    const isAppLink = (u?: string | null): u is string =>
      !!u && /^https?:\/\//i.test(u) && u.toLowerCase().includes(APP_HOST);
    const navigateTo = (u: string) => {
      hasLoadedOnce.current = false; // é um carregamento real → mostra o spinner
      setError(false);
      setLoading(true);
      setCurrentUri(u);
    };
    Linking.getInitialURL().then((u) => { if (isAppLink(u)) navigateTo(u); }).catch(() => {});
    const sub = Linking.addEventListener('url', ({ url }) => { if (isAppLink(url)) navigateTo(url); });
    return () => sub.remove();
  }, []);

  const onNavChange = useCallback((navState: WebViewNavigation) => {
    setCanGoBack(navState.canGoBack);
    // Garante que o overlay nunca fique preso: quando o WebView reporta que não
    // está mais carregando, escondemos o spinner.
    if (!navState.loading) setLoading(false);
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
    hasLoadedOnce.current = false; // retry após erro é um carregamento real → mostra spinner
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
            source={{ uri: currentUri }}
            applicationNameForUserAgent="TenfyMobileApp"
            injectedJavaScriptBeforeContentLoaded={INJECT_PLATFORM}
            originWhitelist={['*']}
            javaScriptEnabled
            domStorageEnabled
            sharedCookiesEnabled
            thirdPartyCookiesEnabled
            allowsBackForwardNavigationGestures
            pullToRefreshEnabled
            mediaPlaybackRequiresUserAction
            setSupportMultipleWindows={false}
            onLoadStart={() => { if (!hasLoadedOnce.current) setLoading(true); }}
            onLoadEnd={() => {
              hasLoadedOnce.current = true;
              setLoading(false);
              // Reentrega o push token ao web a cada carga (login, navegação, retorno).
              if (pushTokenRef.current) {
                webRef.current?.injectJavaScript(pushTokenJS(pushTokenRef.current));
              }
            }}
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
