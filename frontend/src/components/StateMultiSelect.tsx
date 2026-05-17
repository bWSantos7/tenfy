import React, { useRef, useState, useEffect } from 'react';
import { ChevronDown, X } from 'lucide-react';

const ALL_UFS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB',
  'PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];

const UF_LABELS: Record<string, string> = {
  AC:'Acre', AL:'Alagoas', AP:'Amapá', AM:'Amazonas', BA:'Bahia', CE:'Ceará',
  DF:'Distrito Federal', ES:'Espírito Santo', GO:'Goiás', MA:'Maranhão',
  MT:'Mato Grosso', MS:'Mato Grosso do Sul', MG:'Minas Gerais', PA:'Pará',
  PB:'Paraíba', PR:'Paraná', PE:'Pernambuco', PI:'Piauí', RJ:'Rio de Janeiro',
  RN:'Rio Grande do Norte', RS:'Rio Grande do Sul', RO:'Rondônia', RR:'Roraima',
  SC:'Santa Catarina', SP:'São Paulo', SE:'Sergipe', TO:'Tocantins',
};

interface Props {
  label?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export const StateMultiSelect: React.FC<Props> = ({
  label = 'Estados onde aceita jogar',
  values,
  onChange,
  placeholder = 'Selecione os estados...',
}) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const isAll = values.length === ALL_UFS.length;

  function toggleAll() {
    onChange(isAll ? [] : [...ALL_UFS]);
  }

  function toggle(uf: string) {
    if (values.includes(uf)) {
      onChange(values.filter((v) => v !== uf));
    } else {
      onChange([...values, uf]);
    }
  }

  function getLabel(): string {
    if (values.length === 0) return placeholder;
    if (isAll) return 'Todo o Brasil (todos os estados)';
    if (values.length <= 3) return values.join(', ');
    return `${values.length} estados selecionados`;
  }

  return (
    <div ref={ref} className="relative">
      {label && <label className="text-xs text-text-secondary mb-1 block">{label}</label>}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="input-base flex items-center justify-between text-left w-full"
      >
        <span className={values.length === 0 ? 'text-text-muted' : 'text-text-primary'}>
          {getLabel()}
        </span>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {values.length > 0 && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onChange([]); }}
              className="text-text-muted hover:text-text-primary p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          )}
          <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-bg-card border border-border-subtle rounded-xl shadow-xl overflow-hidden">
          {/* Todo o Brasil */}
          <div
            className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-bg-elevated border-b border-border-subtle ${isAll ? 'bg-accent-neon/10' : ''}`}
            onClick={toggleAll}
          >
            <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 ${isAll ? 'border-accent-neon bg-accent-neon' : 'border-border-subtle'}`}>
              {isAll && <svg className="w-2.5 h-2.5 text-bg-base" fill="none" viewBox="0 0 12 12"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
            </div>
            <span className="text-sm font-medium">Todo o Brasil (todos os estados)</span>
          </div>

          {/* States list */}
          <div className="max-h-48 overflow-y-auto">
            {ALL_UFS.map((uf) => {
              const checked = values.includes(uf);
              return (
                <div
                  key={uf}
                  className={`flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-bg-elevated ${checked ? 'bg-accent-neon/5' : ''}`}
                  onClick={() => toggle(uf)}
                >
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 ${checked ? 'border-accent-neon bg-accent-neon' : 'border-border-subtle'}`}>
                    {checked && <svg className="w-2.5 h-2.5 text-bg-base" fill="none" viewBox="0 0 12 12"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </div>
                  <span className="text-sm">{uf} – {UF_LABELS[uf]}</span>
                </div>
              );
            })}
          </div>

          <div className="px-3 py-2 border-t border-border-subtle flex justify-between items-center">
            <span className="text-xs text-text-muted">{values.length} de {ALL_UFS.length} selecionados</span>
            <button type="button" onClick={() => setOpen(false)} className="text-xs text-accent-neon font-medium hover:underline">OK</button>
          </div>
        </div>
      )}
    </div>
  );
};

export { ALL_UFS };
export async function loadCitiesForState(uf: string): Promise<{ value: string; label: string }[]> {
  if (!uf) return [];
  try {
    const res = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/estados/${uf}/municipios`);
    const data: { nome: string }[] = await res.json();
    return data
      .map((c) => ({ value: c.nome, label: c.nome }))
      .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'));
  } catch {
    return [];
  }
}
