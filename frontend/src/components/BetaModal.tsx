import React, { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { User } from '../types';

// Chave única por dispositivo/browser — persiste entre sessões e usuários
const BETA_ACK_KEY = 'tenfy_beta_ack';

export const BetaModal: React.FC<{ user: User | null }> = ({ user }) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Só exibe quando o usuário estiver carregado e nunca tiver confirmado antes
    if (!user) return;
    if (!localStorage.getItem(BETA_ACK_KEY)) {
      setVisible(true);
    }
  }, [user]);

  const dismiss = () => {
    localStorage.setItem(BETA_ACK_KEY, '1');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="bg-bg-card border border-border-subtle rounded-2xl p-8 max-w-md w-full shadow-xl">
        <div className="flex flex-col items-center text-center">
          <div className="w-16 h-16 rounded-full bg-accent-neon/10 border-2 border-accent-neon/30 flex items-center justify-center mb-5">
            <FlaskConical className="w-8 h-8 text-accent-neon" />
          </div>

          <h2 className="text-xl font-bold text-text-primary mb-3">Versão Beta</h2>

          <p className="text-text-secondary text-sm leading-relaxed mb-6">
            Você está acessando uma versão beta do Tenfy (MVP). O app ainda está em testes e pode conter erros ou instabilidades.
            <br /><br />
            Neste período, a criação de conta é gratuita e todas as funcionalidades disponíveis estão liberadas.
          </p>

          <button
            onClick={dismiss}
            className="w-full btn-primary py-3 text-base font-semibold"
          >
            Entendi
          </button>
        </div>
      </div>
    </div>
  );
};
