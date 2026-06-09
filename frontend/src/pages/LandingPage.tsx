import React, { useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
// HTML original da landing (src/landing/index.html), importado como texto cru.
// Mantido sem alterações; aqui só ajustamos os caminhos relativos para absolutos.
import rawHtml from '../landing/index.html?raw';

/**
 * A landing é o documento original (src/landing/index.html) renderizado dentro de um
 * iframe via `srcDoc`. Isso o isola 100% do CSS do app (Tailwind/globals.css) — então
 * o layout, espaçamentos, imagens, fontes e animações ficam idênticos ao arquivo original.
 *
 * Os assets e scripts (imagens, landing-v2.js, image-slot.js) são servidos estaticamente
 * de /tenfy-landing/. Só reescrevemos os caminhos relativos do HTML para absolutos.
 * A navegação dos botões de login/cadastro é conectada por cima (mesmo documento), sem
 * modificar o HTML da landing.
 */
const SRC_DOC = rawHtml
  .replace(/(["'(])assets\//g, '$1/tenfy-landing/assets/')
  .replace(/src=(["'])image-slot\.js\1/g, 'src=$1/tenfy-landing/image-slot.js$1')
  .replace(/src=(["'])landing-v2\.js\1/g, 'src=$1/tenfy-landing/landing-v2.js$1');

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const srcDoc = useMemo(() => SRC_DOC, []);

  // Detecta se está rodando dentro do app mobile (WebView)
  const isMobileApp = useMemo(() => {
    return (
      navigator.userAgent.includes('TenfyMobileApp') ||
      !!(window as any).ReactNativeWebView
    );
  }, []);

  useEffect(() => {
    if (isMobileApp) {
      // Redireciona para /inicio (o ProtectedRoute mandará para /login se não logado)
      navigate('/inicio', { replace: true });
    }
  }, [isMobileApp, navigate]);

  if (isMobileApp) {
    return (
      <div className="min-h-screen bg-[#F6F7FA] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0A1330] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const onLoad = useCallback(
    (e: React.SyntheticEvent<HTMLIFrameElement>) => {
      const doc = e.currentTarget.contentDocument;
      if (!doc) return;

      const go = (path: string) => (ev: Event) => {
        ev.preventDefault();
        navigate(path);
      };

      // Âncoras internas (#recursos, #como, #app, #top): num iframe srcDoc o href "#x"
      // resolve contra a URL da página pai, então o scroll nativo não funciona.
      // Rolamos manualmente para o elemento dentro do documento do iframe.
      const scrollToHash = (hash: string) => (ev: Event) => {
        const id = (hash || '').replace('#', '');
        const target = id ? doc.getElementById(id) : null;
        if (target) {
          ev.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      };

      doc.querySelectorAll<HTMLAnchorElement>('.nav-links a, .nav-logo, a.btn-ghost').forEach((a) =>
        a.addEventListener('click', scrollToHash(a.getAttribute('href') || '#top')),
      );

      doc.querySelectorAll('.nav-cta .login').forEach((a) => a.addEventListener('click', go('/login')));
      doc.querySelectorAll('.signup, .btn-lime, .split-copy .more').forEach((a) =>
        a.addEventListener('click', go('/register')),
      );
      doc.querySelectorAll<HTMLAnchorElement>('.foot-col a').forEach((a) => {
        const t = (a.textContent || '').trim().toLowerCase();
        const href = a.getAttribute('href') || '';
        if (t === 'privacidade' || t === 'termos') a.addEventListener('click', go('/politica-privacidade'));
        else if (t === 'criar conta') a.addEventListener('click', go('/register'));
        else if (t === 'web') a.addEventListener('click', go('/login'));
        else if (href.startsWith('#')) a.addEventListener('click', scrollToHash(href));
      });
    },
    [navigate],
  );

  return (
    <iframe
      title="Tenfy — A quadra te espera"
      srcDoc={srcDoc}
      onLoad={onLoad}
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', border: 0 }}
    />
  );
};
