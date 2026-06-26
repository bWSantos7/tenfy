// Detecção do contexto de execução: app mobile (WebView nativa) vs navegador comum.
//
// A casca nativa (mobile/) injeta `window.__TENFY_APP_OS__` ('ios' | 'android') antes
// de carregar o conteúdo e define o User-Agent com "TenfyMobileApp". Usamos ambos os
// sinais para robustez (a injeção pode não rodar em iframes srcDoc; a UA é o fallback).
//
// Motivação: na App Store da Apple, vender assinatura digital por gateway externo dentro
// do app aciona a regra de In-App Purchase (3.1.1). Por isso, no app iOS, cadastro e
// checkout ficam ocultos — o app funciona apenas com login (modelo "conta externa").
// No Android nada muda: a Play Store já aprovou o checkout atual.

function ua(): string {
  return typeof navigator !== 'undefined' ? navigator.userAgent || '' : '';
}

/** True quando rodando dentro da casca mobile (iOS ou Android). */
export function isMobileApp(): boolean {
  if (typeof window === 'undefined') return false;
  return ua().includes('TenfyMobileApp') || !!(window as any).ReactNativeWebView;
}

/** Sistema do app mobile, quando detectável. */
export function appOS(): 'ios' | 'android' | null {
  if (typeof window === 'undefined') return null;
  const injected = (window as any).__TENFY_APP_OS__;
  if (injected === 'ios' || injected === 'android') return injected;
  if (!isMobileApp()) return null;
  if (/iPad|iPhone|iPod/i.test(ua())) return 'ios';
  if (/Android/i.test(ua())) return 'android';
  return null;
}

/**
 * True somente no app iOS. É o gate de conformidade Apple: oculta cadastro,
 * planos, preços e qualquer checkout, deixando o app apenas com login.
 */
export function isIosApp(): boolean {
  return isMobileApp() && appOS() === 'ios';
}
