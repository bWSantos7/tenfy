import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, ArrowRight, CheckCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { createProfile, listProfiles } from '../services/data';
import { extractApiError } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { LEVEL_LABELS, TENNIS_CLASS_LABELS } from '../utils/format';
import { StateMultiSelect, loadCitiesForState } from '../components/StateMultiSelect';

const UF_OPTIONS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

export const OnboardingPage: React.FC = () => {
  const nav = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);

  const [form, setForm] = useState({
    display_name: '',
    birth_year: '',
    gender: '' as 'M' | 'F' | '',
    home_state: 'SP',
    home_city: '',
    travel_states: [] as string[],
    competitive_level: 'amateur',
    tennis_class: '',
  });

  // IBGE cities
  const [cities, setCities] = useState<{ value: string; label: string }[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);

  function update<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  useEffect(() => {
    (async () => {
      try {
        const profiles = await listProfiles().catch(() => []);
        if (user?.role === 'player' && profiles.length > 0) {
          toast('Seu perfil deve ser editado na aba Perfil.');
          nav('/perfil', { replace: true });
          return;
        }
      } finally {
        setCheckingAccess(false);
      }
    })();
  }, [nav, user?.role]);

  // Load cities when state changes on step 2
  useEffect(() => {
    if (step === 2) {
      setLoadingCities(true);
      loadCitiesForState(form.home_state)
        .then(setCities)
        .finally(() => setLoadingCities(false));
    }
  }, [form.home_state, step]);

  function handleTravelStates(vals: string[]) {
    const ALL_UFS_SET = new Set(UF_OPTIONS);
    const hasAll = vals.every((v) => ALL_UFS_SET.has(v)) && vals.length === UF_OPTIONS.length;
    if (vals.includes('__ALL__') || hasAll) {
      update('travel_states', [...UF_OPTIONS]);
    } else {
      update('travel_states', vals);
    }
  }

  async function finish() {
    setSubmitting(true);
    try {
      await createProfile({
        display_name: form.display_name || 'Jogador',
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        gender: form.gender || undefined,
        home_state: form.home_state,
        home_city: form.home_city,
        travel_states: form.travel_states,
        competitive_level: form.competitive_level as any,
        tennis_class: form.tennis_class,
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
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col px-4 py-6">
      <div className="max-w-md w-full mx-auto">
        {/* Progress bar */}
        <div className="mb-6">
          <div className="flex items-center justify-between text-xs text-text-muted mb-2">
            <span>Passo {step} de 3</span>
            <span>{Math.round((step / 3) * 100)}%</span>
          </div>
          <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
            <div className="h-full bg-accent-neon rounded-full transition-all shadow-glow"
              style={{ width: `${(step / 3) * 100}%` }} />
          </div>
        </div>

        {/* ─── Step 1: Dados pessoais ───────────────────────────────────── */}
        {step === 1 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Vamos começar</h2>
              <p className="text-sm text-text-secondary">Como devemos te chamar?</p>
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nome de exibição</label>
              <input className="input-base" value={form.display_name}
                onChange={(e) => update('display_name', e.target.value)}
                placeholder="Ex: João Silva" />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Ano de nascimento</label>
              <input type="number" min={1900} max={new Date().getFullYear()}
                className="input-base" placeholder="Ex: 1990"
                value={form.birth_year}
                onChange={(e) => update('birth_year', e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-text-secondary mb-1 block">Gênero</label>
              <select className="input-base" value={form.gender}
                onChange={(e) => update('gender', e.target.value as 'M' | 'F' | '')}>
                <option value="">Selecione...</option>
                <option value="M">Masculino</option>
                <option value="F">Feminino</option>
              </select>
            </div>
            <button className="btn-primary w-full flex items-center justify-center gap-2"
              onClick={() => setStep(2)} disabled={!form.display_name}>
              Continuar <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ─── Step 2: Localização e estados ───────────────────────────── */}
        {step === 2 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Onde você joga?</h2>
              <p className="text-sm text-text-secondary">Isso nos ajuda a encontrar torneios relevantes.</p>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Estado (UF)</label>
                <select className="input-base" value={form.home_state}
                  onChange={(e) => { update('home_state', e.target.value); update('home_city', ''); }}>
                  {UF_OPTIONS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-text-secondary mb-1 block">Cidade</label>
                {cities.length > 0 ? (
                  <select className="input-base" value={form.home_city}
                    onChange={(e) => update('home_city', e.target.value)}>
                    <option value="">{loadingCities ? 'Carregando...' : 'Selecione a cidade'}</option>
                    {cities.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                ) : (
                  <input className="input-base" placeholder={loadingCities ? 'Carregando...' : 'Cidade'} value={form.home_city}
                    onChange={(e) => update('home_city', e.target.value)} />
                )}
              </div>
            </div>

            {/* Estados onde aceita jogar — substituiu travel_radius_km */}
            <StateMultiSelect
              values={form.travel_states}
              onChange={handleTravelStates}
            />

            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep(1)}>Voltar</button>
              <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={() => setStep(3)}>
                Continuar <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* ─── Step 3: Nível ────────────────────────────────────────────── */}
        {step === 3 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-xl font-bold mb-1">Seu nível</h2>
              <p className="text-sm text-text-secondary">Determina os torneios compatíveis com você.</p>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Nível competitivo</label>
              <select className="input-base" value={form.competitive_level}
                onChange={(e) => update('competitive_level', e.target.value)}>
                {Object.entries(LEVEL_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Classe (FPT / federação)</label>
              <select className="input-base" value={form.tennis_class}
                onChange={(e) => update('tennis_class', e.target.value)}>
                <option value="">Sem classe definida</option>
                {Object.entries(TENNIS_CLASS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            <div className="flex gap-2">
              <button className="btn-secondary flex-1" onClick={() => setStep(2)}>Voltar</button>
              <button className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={finish} disabled={submitting}>
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCheck className="w-4 h-4" />}
                Concluir
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
