import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle, Clock, CreditCard } from 'lucide-react';
import { fetchSubscription } from '../services/billing';

type Status = 'checking' | 'active' | 'pending';

export const PaymentReturnPage: React.FC = () => {
  const nav = useNavigate();
  const [status, setStatus] = useState<Status>('checking');
  const [attempts, setAttempts] = useState(0);
  const canceled = new URLSearchParams(window.location.search).get('status') === 'cancelado';

  const check = useCallback(async () => {
    setStatus('checking');
    try {
      const s = await fetchSubscription();
      setStatus(s.status === 'active' || s.status === 'trial' ? 'active' : 'pending');
    } catch {
      setStatus('pending');
    }
  }, []);

  // Verifica ao montar e, se ainda pendente, refaz algumas vezes (webhook é assíncrono).
  useEffect(() => { check(); }, [check]);
  useEffect(() => {
    if (status !== 'pending' || attempts >= 5) return;
    const t = setTimeout(() => { setAttempts((a) => a + 1); check(); }, 4000);
    return () => clearTimeout(t);
  }, [status, attempts, check]);

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
              <p className="text-sm text-text-muted mt-1">Sua assinatura está ativa.</p>
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
                  : 'Assim que o pagamento for confirmado, seu acesso é liberado. Pode levar alguns instantes.'}
              </p>
            </div>
            <button className="btn-primary w-full" onClick={check}>
              Verificar novamente
            </button>
            <button className="btn-secondary w-full flex items-center justify-center gap-2" onClick={() => nav('/assinatura', { replace: true })}>
              <CreditCard className="w-4 h-4" /> Escolher forma de pagamento
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
