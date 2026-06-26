import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { exchangeAppHandoff } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';

/**
 * Destino do "retorno automático logado". O site (no Safari), após o usuário criar a conta
 * e assinar, monta um universal link para esta rota com um token de uso único (?ht=). Ao
 * abrir o app, a WebView carrega `/app/continuar?ht=...`, troca o token por uma sessão JWT
 * e entra direto — sem o usuário digitar a senha de novo.
 *
 * Se o app não estiver instalado, o universal link cai aqui no próprio Safari: a troca
 * também funciona e o usuário continua logado na web. Sem becos sem saída.
 */
export const AppHandoffPage: React.FC = () => {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [failed, setFailed] = useState(false);
  // StrictMode (dev) monta o efeito duas vezes; o token é de uso único, então a 2ª troca
  // falharia. Garante uma única tentativa.
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const token = new URLSearchParams(window.location.search).get('ht') || '';
    if (!token) {
      nav('/login', { replace: true });
      return;
    }

    exchangeAppHandoff(token)
      .then((data) => {
        setUser(data.user);
        nav('/inicio', { replace: true });
      })
      .catch(() => setFailed(true));
  }, [nav, setUser]);

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-6">
          <img src="/logos/logo_clara.png" alt="Tenfy" className="h-24 w-auto object-contain dark:hidden" />
          <img src="/logos/logo_escura.png" alt="Tenfy" className="h-14 w-auto object-contain hidden dark:block" />
        </div>

        {!failed ? (
          <div className="card text-center py-10 space-y-3">
            <Loader2 className="w-9 h-9 text-accent-neon animate-spin mx-auto" />
            <p className="font-semibold">Entrando…</p>
            <p className="text-xs text-text-muted">Conectando sua conta ao app.</p>
          </div>
        ) : (
          <div className="card text-center py-10 space-y-4">
            <div>
              <p className="font-semibold text-lg">Não foi possível entrar automaticamente</p>
              <p className="text-sm text-text-muted mt-1">
                O link pode ter expirado. Faça login com seu e-mail e senha.
              </p>
            </div>
            <button className="btn-primary w-full" onClick={() => nav('/login', { replace: true })}>
              Ir para o login
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
