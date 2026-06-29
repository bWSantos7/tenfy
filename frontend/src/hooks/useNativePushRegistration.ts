import { useEffect, useRef } from 'react';
import api from '../services/api';

/**
 * Registra o push token nativo (iOS/Android) no backend, associado ao usuário logado.
 *
 * A casca mobile obtém o ExponentPushToken e o injeta na WebView em
 * `window.__TENFY_PUSH_TOKEN__`, disparando o evento `tenfy-push-token`. Aqui — onde existe
 * o JWT — registramos o token em `/api/alerts/register-device/`. No navegador comum a
 * variável nunca existe, então o hook é no-op. Use dentro da área autenticada.
 */
export function useNativePushRegistration() {
  const registered = useRef<string | null>(null);

  useEffect(() => {
    const register = () => {
      const t = (window as any).__TENFY_PUSH_TOKEN__ as
        | { token?: string; platform?: string }
        | undefined;
      if (!t?.token || registered.current === t.token) return;
      registered.current = t.token;
      api
        .post('/api/alerts/register-device/', { token: t.token, platform: t.platform })
        .catch(() => { registered.current = null; }); // permite nova tentativa depois
    };

    register(); // caso o token já tenha sido injetado antes deste mount
    window.addEventListener('tenfy-push-token', register);
    return () => window.removeEventListener('tenfy-push-token', register);
  }, []);
}
