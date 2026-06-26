import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

/**
 * Push nativo (iOS/Android). É o valor nativo que sustenta o app além de uma casca web:
 * o Web Push não funciona na WebView do iOS, então as notificações reais vêm por aqui.
 *
 * O app só obtém o token; quem o associa ao usuário é o web (que tem o JWT) — o token é
 * injetado na WebView e registrado em POST /api/alerts/register-device/. Veja WebAppShell.
 */

// projectId é público (já consta em app.json) — necessário para o token em build EAS.
const PROJECT_ID =
  (Constants.expoConfig?.extra as any)?.eas?.projectId ||
  '1bbf218d-0dd0-418a-9d42-0d73915996a3';

export type PushToken = { token: string; platform: 'ios' | 'android' };

// Notificações em primeiro plano aparecem como banner (a WebView ocupa a tela toda).
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/**
 * Pede permissão (se necessário) e devolve o ExponentPushToken do dispositivo.
 * Retorna null quando o usuário nega ou em ambiente sem push (ex.: simulador).
 */
export async function registerForPushToken(): Promise<PushToken | null> {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Tenfy',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  const current = await Notifications.getPermissionsAsync();
  let status = current.status;
  if (status !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== 'granted') return null;

  try {
    const { data } = await Notifications.getExpoPushTokenAsync({ projectId: PROJECT_ID });
    if (!data) return null;
    return { token: data, platform: Platform.OS === 'ios' ? 'ios' : 'android' };
  } catch {
    return null;
  }
}
