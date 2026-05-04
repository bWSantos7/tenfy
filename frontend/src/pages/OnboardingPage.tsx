import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, ArrowRight, CheckCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { createProfile, listProfiles } from '../services/data';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const STATES = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

const LEVELS: { value: string; label: string }[] = [
  { value: 'beginner', label: 'Principiante' },
  { value: 'amateur', label: 'Amador' },
  { value: 'federated', label: 'Federado' },
  { value: 'youth', label: 'Juvenil' },
  { value: 'pro', label: 'Profissional' },
];

const CLASSES = ['1', '2', '3', '4', '5', 'PR'];

export const OnboardingPage: React.FC = () => {
  const nav = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [form, setForm] = useState({
    display_name: '',
    birth_year: '' as string | number,
    gender: '' as 'M' | 'F' | '',
    home_state: 'SP',
    home_city: '',
    travel_radius_km: 100,
    competitive_level: 'amateur',
    tennis_class: '',
    dominant_hand: '' as 'R' | 'L' | '',
  });

  function update<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  useEffect(() => {
    (async () => {
      try {
        const profiles = await listProfiles().catch(() => []);
        if (user?.role === 'player' && profiles.length > 0) {
          toast('Seu perfil de jogador deve ser mantido e editado na aba Perfil.');
          nav('/perfil', { replace: true });
          return;
        }
      } finally {
        setCheckingAccess(false);
      }
    })();
  }, [nav, user?.role]);

  async function finish() {
    setSubmitting(true);
    try {
      await createProfile({
        display_name: form.display_name || 'Jogador',
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        gender: form.gender || undefined,
        home_state: form.home_state,
        home_city: form.home_city,
        travel_radius_km: form.travel_radius_km,
        competitive_level: form.competitive_level as any,
        tennis_class: form.tennis_class,
        dominant_hand: form.dominant_hand || undefined,
        is_primary: true,
      } as any);
      toast.success('Perfil criado!');
      nav('/', { replace: true });
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (checkingAccess) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center px-4 py-6">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col px-4 py-6">
      <div className="max-w-md w-full mx-auto">
        <div className="mb-6">
          <div className="flex items-center gap-2 text-xs text-text-muted mb-2">
            <span>Passo {step} de 3</span>
          </div>
          <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-neon transition-all shadow-glow"
              style={{ width: `${(step / 3) * 100}%` }}
            />
          </div>
        </div>

        {step === 1 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Vamos começar</h2>
              <p className="text-sm text-text-secondary">Diga como devemos te chamar.</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome (como aparece)</label>
              <input
                className="input-base"
                value={form.display_name}
                onChange={(e) => update('display_name', e.target.value)}
                placeholder="Ex: João Silva"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Ano de nascimento</label>
                <input
                  type="number"
                  min={1900}
                  max={new Date().getFullYear()}
                  className="input-base"
                  placeholder="1990"
                  value={form.birth_year}
                  onChange={(e) => update('birth_year', e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Gênero</label>
                <select
                  className="input-base"
                  value={form.gender}
                  onChange={(e) => update('gender', e.target.value as 'M' | 'F' | '')}
                >
                  <option value="">—</option>
                  <option value="M">Masculino</option>
                  <option value="F">Feminino</option>
                </select>
              </div>
            </div>
            <button
              className="btn-primary w-full flex items-center justify-center gap-2"
              onClick={() => setStep(2)}
              disabled={!form.display_name}
            >
              Continuar <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Onde você joga?</h2>
              <p className="text-sm text-text-secondary">
                Isso nos ajuda a priorizar torneios próximos.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">UF</label>
                <select
                  className="input-base"
                  value={form.home_state}
                  onChange={(e) => update('home_state', e.target.value)}
                >
                  {STATES.map((uf) => (
                    <option key={uf} value={uf}>{uf}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
                <input
                  className="input-base"
                  placeholder="São Paulo"
                  value={form.home_city}
                  onChange={(e) => update('home_city', e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">
                Raio de viagem (km): {form.travel_radius_km}
              </label>
              <input
                type="range"
                min={25}
                max={1000}
                step={25}
                value={form.travel_radius_km}
                onChange={(e) => update('travel_radius_km', Number(e.target.value))}
                className="w-full accent-accent-neon"
              />
            </div>
            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep(1)}>Voltar</button>
              <button
                className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={() => setStep(3)}
              >
                Continuar <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Seu nível</h2>
              <p className="text-sm text-text-secondary">
                Isso determina os torneios compatíveis com você.
              </p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Tipo de jogador</label>
              <select
                className="input-base"
                value={form.competitive_level}
                onChange={(e) => update('competitive_level', e.target.value)}
              >
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">
                Classe (FPT / federação)
              </label>
              <div className="grid grid-cols-3 gap-2">
                {CLASSES.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => update('tennis_class', c === form.tennis_class ? '' : c)}
                    className={`py-2.5 rounded-xl border text-sm font-semibold transition-colors ${
                      form.tennis_class === c
                        ? 'bg-accent-neon text-bg-base border-accent-neon'
                        : 'bg-bg-card border-border-subtle text-text-primary hover:bg-bg-elevated'
                    }`}
                  >
                    {c === 'PR' ? 'Principiante' : `${c}ª`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep(2)}>Voltar</button>
              <button
                className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={finish}
                disabled={submitting}
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCheck className="w-4 h-4" />
                )}
                Concluir
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
