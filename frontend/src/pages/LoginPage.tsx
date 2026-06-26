import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { login } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';
// HTML original da tela de login (src/login/index.html), importado como texto cru.
// Renderizado isolado num iframe (srcDoc) para ficar idêntico ao design original.
import rawHtml from '../login/index.html?raw';

// Caminhos relativos dos assets → absolutos (servidos de /tenfy-login/).
const SRC_DOC = rawHtml.replace(/(["'(])assets\//g, '$1/tenfy-login/assets/');

export const LoginPage: React.FC = () => {
  const nav = useNavigate();
  const location = useLocation();
  const { setUser } = useAuth();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const srcDoc = useMemo(() => SRC_DOC, []);

  const rawFrom = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
  const from = !rawFrom || rawFrom === '/' ? '/inicio' : rawFrom;

  // Recebe o submit do formulário (dentro do iframe) e faz a autenticação real.
  useEffect(() => {
    const handler = async (ev: MessageEvent) => {
      if (ev.source !== iframeRef.current?.contentWindow) return;
      const d = ev.data as { type?: string; email?: string; password?: string } | null;
      if (!d || d.type !== 'tenfy-login') return;
      try {
        const data = await login(String(d.email ?? '').trim(), String(d.password ?? ''));
        setUser(data.user);
        toast.success('Bem-vindo de volta!');
        nav(from, { replace: true });
      } catch (err) {
        // Prefere a mensagem do backend (tentativas restantes / bloqueio temporário);
        // cai num texto genérico quando não há detalhe.
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        const message = detail || 'E-mail ou senha incorretos. Verifique os dados ou redefina sua senha.';
        iframeRef.current?.contentWindow?.postMessage(
          { type: 'tenfy-login-error', message },
          '*',
        );
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [from, nav, setUser]);

  // Liga os links da tela (sem alterar o HTML da pasta).
  const onLoad = useCallback(() => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    const go = (path: string) => (e: Event) => {
      e.preventDefault();
      nav(path);
    };
    doc.querySelector('.back')?.addEventListener('click', go('/'));
    doc.querySelector('.forgot')?.addEventListener('click', go('/recuperar-senha'));
    doc.querySelector('.signup-link')?.addEventListener('click', go('/register'));
    doc.querySelector('.partner-link')?.addEventListener('click', go('/parceiro/login'));
  }, [nav]);

  return (
    <iframe
      ref={iframeRef}
      title="Tenfy — Acesse sua conta"
      srcDoc={srcDoc}
      onLoad={onLoad}
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', border: 0 }}
    />
  );
};
