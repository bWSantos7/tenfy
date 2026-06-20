import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle, Clock, CreditCard } from 'lucide-react';
import { fetchSubscription } from '../services/billing';
import { registerStatus } from '../services/auth';
import { useAuth } from '../contexts/AuthContext';

type Status = 'checking' | 'active' | 'pending';

// O webhook do Asaas (sobretudo Pix) pode levar mais que alguns segundos.
// Consulta a cada 5s por ~2 minutos antes de oferecer o retry manual.
const POLL_INTERVAL_MS = 5000;
const MAX_ATTEMPTS = 24;

export const PaymentReturnPage: React.FC = () => {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const params = new URLSearchParams(window.location.search);
  const regToken = params.get('reg') || '';
  const canceled = params.get('status') === 'cancelado';

  const [status, setStatus] = useState<Status>('checking');
  const [attempts, setAttempts] = useState(0);

  const check = useCallback(async () => {
    setStatus('checking');
    try {
      if (regToken) {
        // Cadastro diferido: a conta só nasce quando o pagamento confirma.
        const r = await registerStatus(regToken);
        if (r.ready && r.user) {
          setUser(r.user);
          setStatus('active');
        } else {
          setStatus('pending');
        }
      } else {
        // Upgrade de usuário já existente (autenticado).
        const s = await fetchSubscription();
        setStatus(s.status === 'active' || s.status === 'trial' ? 'active' : 'pending');
      }
    } catch {
      setStatus('pending');
    }
  }, [regToken, setUser]);

  useEffect(() => { check(); }, [check]);
  useEffect(() => {
    if (status !== 'pending' || canceled || attempts >= MAX_ATTEMPTS) return;
    const t = setTimeout(() => { setAttempts((a) => a + 1); check(); }, POLL_INTERVAL_MS);
    return () => clearTimeout(t);
  }, [status, attempts, canceled, check]);

  // Confirmou: leva o usuário para o app automaticamente (não fica preso na tela).
  useEffect(() => {
    if (status !== 'active') return;
    const t = setTimeout(() => nav('/inicio', { replace: true }), 1800);
    return () => clearTimeout(t);
  }, [status, nav]);

  return (
    <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-6">
          <img src="/logos/logo_clara.png" alt="Tenfy" className="h-24 w-auto object-contain dark:hidden" />
          <img src="/logos/logo_escura.png" alt="Tenfy" className="h-14 w-auto object-contain hidden dark:block" />
        </div>

        {status === 'checking' && (
          <div className="card text-center py-10 space-y-3">
            <Loader2 className="w-9 h-9 text-accent-neon animate-spin mx-auto" />
            <p className="font-semibold">Confirmando seu pagamento…</p>
            <p className="text-xs text-text-muted">Isso leva alguns instantes.</p>
          </div>
        )}

        {status === 'active' && (
          <div className="card text-center py-10 space-y-4">
            <CheckCircle className="w-12 h-12 text-accent-neon mx-auto" />
            <div>
              <p className="font-semibold text-lg">Pagamento confirmado!</p>
              <p className="text-sm text-text-muted mt-1">Sua conta está ativa.</p>
            </div>
            <button className="btn-primary w-full" onClick={() => nav('/inicio', { replace: true })}>
              Entrar no app
            </button>
          </div>
        )}

        {status === 'pending' && (
          <div className="card text-center py-10 space-y-4">
            <Clock className="w-12 h-12 text-amber-400 mx-auto" />
            <div>
              <p className="font-semibold text-lg">
                {canceled ? 'Pagamento não concluído' : 'Aguardando confirmação'}
              </p>
              <p className="text-sm text-text-muted mt-1">
                {canceled
                  ? 'Você pode tentar novamente ou escolher outra forma de pagamento.'
                  : 'Assim que o pagamento for confirmado, sua conta é criada e o acesso liberado. Pode levar alguns instantes.'}
              </p>
            </div>
            <button className="btn-primary w-full" onClick={check}>
              Verificar novamente
            </button>
            <button className="btn-secondary w-full flex items-center justify-center gap-2" onClick={() => nav('/login', { replace: true })}>
              <CreditCard className="w-4 h-4" /> Voltar ao início
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
