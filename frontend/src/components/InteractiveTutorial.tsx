import React, { useCallback, useEffect, useState } from 'react';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import { User } from '../types';
import { getTutorialSteps } from '../data/helpContent';

// Chave por usuário — cada conta vê o tutorial automático uma única vez.
const tutorialDoneKey = (userId: number) => `tenfy_tutorial_done_${userId}`;

// Evento para reabrir o tutorial manualmente (botão "Rever tutorial" na Ajuda).
export const OPEN_TUTORIAL_EVENT = 'tenfy-open-tutorial';
// Disparado pelo BetaModal ao ser fechado, para encadear o tutorial sem sobrepor.
export const BETA_ACK_EVENT = 'tenfy-beta-ack';
const betaAckKey = (userId: number) => `tenfy_beta_ack_${userId}`;

export const InteractiveTutorial: React.FC<{ user: User | null }> = ({ user }) => {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  // Imagens que falharam ao carregar — caem para o ícone como fallback.
  const [brokenImages, setBrokenImages] = useState<Record<string, boolean>>({});

  const steps = getTutorialSteps(user?.role);

  const open = useCallback(() => { setStep(0); setVisible(true); }, []);

  // Mostra automaticamente no primeiro acesso — mas só depois que o aviso de
  // beta já foi confirmado, para os dois modais não aparecerem ao mesmo tempo.
  useEffect(() => {
    if (!user) return;
    const done = localStorage.getItem(tutorialDoneKey(user.id));
    const betaAck = localStorage.getItem(betaAckKey(user.id));
    if (!done && betaAck) open();
  }, [user, open]);

  // Encadeia após o fechamento do BetaModal e permite reabrir pela Ajuda.
  useEffect(() => {
    if (!user) return;
    const onBetaAck = () => {
      if (!localStorage.getItem(tutorialDoneKey(user.id))) open();
    };
    window.addEventListener(BETA_ACK_EVENT, onBetaAck);
    window.addEventListener(OPEN_TUTORIAL_EVENT, open);
    return () => {
      window.removeEventListener(BETA_ACK_EVENT, onBetaAck);
      window.removeEventListener(OPEN_TUTORIAL_EVENT, open);
    };
  }, [user, open]);

  // Fechar ou concluir marca como visto: não reaparece nos próximos acessos.
  const finish = () => {
    if (user) {
      try { localStorage.setItem(tutorialDoneKey(user.id), '1'); } catch { /* ignore */ }
    }
    setVisible(false);
  };

  if (!visible || steps.length === 0) return null;

  const isLast = step >= steps.length - 1;
  const current = steps[step];
  const Icon = current.icon;
  const showImage = !!current.image && !brokenImages[current.image];

  return (
    <div className="fixed inset-0 z-[9998] bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6">
      <div className="bg-bg-card border border-border-subtle rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Cabeçalho */}
        <div className="flex items-center justify-between px-5 pt-3 shrink-0">
          <span className="text-[11px] font-semibold text-text-muted">
            Passo {step + 1} de {steps.length}
          </span>
          <button onClick={finish} className="btn-ghost !px-2 text-text-muted" title="Fechar tutorial" aria-label="Fechar tutorial">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Imagem da tela (ou ícone como fallback) + conteúdo — rolável */}
        <div className="overflow-y-auto px-5 pt-2 pb-1">
          {showImage ? (
            <img
              src={current.image}
              alt={current.title}
              onError={() => setBrokenImages((m) => ({ ...m, [current.image as string]: true }))}
              className="w-full rounded-xl border border-border-subtle bg-bg-elevated object-contain max-h-[52vh]"
            />
          ) : (
            <div className="flex justify-center py-4">
              <div className="w-16 h-16 rounded-full bg-accent-neon/10 border-2 border-accent-neon/30 flex items-center justify-center">
                <Icon className="w-8 h-8 text-accent-neon" />
              </div>
            </div>
          )}

          <h2 className="text-lg font-bold text-text-primary mt-3 mb-1">{current.title}</h2>
          <p className="text-sm text-text-secondary leading-relaxed">{current.body}</p>
          {current.hint && (
            <p className="text-xs text-accent-blue mt-2 bg-accent-blue/10 rounded-lg px-3 py-2">
              {current.hint}
            </p>
          )}
        </div>

        {/* Indicadores de progresso */}
        <div className="flex justify-center flex-wrap gap-1.5 py-3 shrink-0">
          {steps.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${i === step ? 'w-5 bg-accent-neon' : 'w-1.5 bg-border-subtle'}`}
            />
          ))}
        </div>

        {/* Navegação */}
        <div className="flex items-center gap-2 px-5 pb-4 shrink-0">
          {step > 0 ? (
            <button onClick={() => setStep((s) => s - 1)} className="btn-secondary !text-sm flex items-center gap-1">
              <ChevronLeft className="w-4 h-4" /> Voltar
            </button>
          ) : (
            <button onClick={finish} className="btn-ghost !text-sm text-text-muted">
              Pular
            </button>
          )}
          <div className="flex-1" />
          {isLast ? (
            <button onClick={finish} className="btn-primary !text-sm">Concluir</button>
          ) : (
            <button onClick={() => setStep((s) => s + 1)} className="btn-primary !text-sm flex items-center gap-1">
              Próximo <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
