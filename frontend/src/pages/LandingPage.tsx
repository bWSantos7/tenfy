import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * A landing page é servida exatamente como a pasta original (frontend/public/tenfy-landing/),
 * exibida num iframe em tela cheia. Isso garante que o HTML/CSS/JS originais rendam
 * idênticos — sem qualquer interferência do CSS do app (Tailwind/globals.css).
 *
 * Os arquivos da pasta NÃO são modificados: a navegação dos botões de login/cadastro
 * é conectada aqui, por cima, acessando o documento do iframe (mesma origem) no onLoad.
 */
export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  const onLoad = useCallback(
    (e: React.SyntheticEvent<HTMLIFrameElement>) => {
      const doc = e.currentTarget.contentDocument;
      if (!doc) return;

      const go = (path: string) => (ev: Event) => {
        ev.preventDefault();
        navigate(path);
      };

      // Entrar → /login
      doc.querySelectorAll('.nav-cta .login').forEach((a) => a.addEventListener('click', go('/login')));

      // Criar conta grátis / CTAs principais → /register
      doc.querySelectorAll('.signup, .btn-lime, .split-copy .more').forEach((a) =>
        a.addEventListener('click', go('/register')),
      );

      // Rodapé: rotas reais por texto do link
      doc.querySelectorAll<HTMLAnchorElement>('.foot-col a').forEach((a) => {
        const t = (a.textContent || '').trim().toLowerCase();
        if (t === 'privacidade' || t === 'termos') a.addEventListener('click', go('/politica-privacidade'));
        else if (t === 'criar conta') a.addEventListener('click', go('/register'));
        else if (t === 'web') a.addEventListener('click', go('/login'));
      });
    },
    [navigate],
  );

  return (
    <iframe
      title="Tenfy — A quadra te espera"
      src="/tenfy-landing/index.html"
      onLoad={onLoad}
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', border: 0 }}
    />
  );
};
