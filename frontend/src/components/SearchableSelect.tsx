import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, X, Search } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
}

interface Props {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  /** Mostra o botão de limpar (volta para ''). */
  allowClear?: boolean;
  /** Texto exibido quando a busca não encontra nada. */
  emptyText?: string;
  className?: string;
  'data-testid'?: string;
}

/** Remove acentos + caixa para busca tolerante. */
function norm(s: string): string {
  return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

/**
 * Combobox com caixa de busca interna (Card 6 tasks2).
 * - Busca parcial, ignorando acentos e maiúsculas/minúsculas.
 * - Navegação por teclado (↑ ↓ Enter Esc).
 * - Mensagem de "nenhum resultado".
 * - Visual padrão Tenfy (input-base + dropdown).
 */
export const SearchableSelect: React.FC<Props> = ({
  label,
  value,
  onChange,
  options,
  placeholder = 'Selecione...',
  disabled = false,
  allowClear = false,
  emptyText = 'Nenhum resultado encontrado',
  className = '',
  'data-testid': testId,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value) || null;

  const filtered = useMemo(() => {
    const q = norm(query);
    if (!q) return options;
    return options.filter((o) => norm(o.label).includes(q));
  }, [options, query]);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIdx(0);
      // foca o campo de busca ao abrir
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // mantém a opção ativa visível ao navegar por teclado
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[activeIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIdx, open]);

  function choose(opt: SelectOption) {
    onChange(opt.value);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      setOpen(true);
      e.preventDefault();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = filtered[activeIdx];
      if (opt) choose(opt);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      {label && <label className="text-xs text-text-secondary mb-1 block">{label}</label>}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onKeyDown}
        className="input-base flex items-center justify-between text-left w-full disabled:opacity-50"
        data-testid={testId}
      >
        <span className={selected ? 'text-text-primary truncate' : 'text-text-muted truncate'}>
          {selected ? selected.label : placeholder}
        </span>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {allowClear && value && !disabled && (
            <span
              role="button"
              tabIndex={-1}
              onClick={(e) => { e.stopPropagation(); onChange(''); }}
              className="text-text-muted hover:text-text-primary p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
          <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-bg-card border border-border-subtle rounded-xl shadow-xl overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle">
            <Search className="w-4 h-4 text-text-muted shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => { setQuery(e.target.value); setActiveIdx(0); }}
              onKeyDown={onKeyDown}
              placeholder="Buscar..."
              className="flex-1 bg-transparent outline-none text-sm text-text-primary placeholder:text-text-muted"
            />
          </div>
          <div ref={listRef} className="max-h-60 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-sm text-text-muted text-center">{emptyText}</div>
            ) : (
              filtered.map((opt, i) => (
                <div
                  key={opt.value || `__empty_${i}`}
                  onMouseEnter={() => setActiveIdx(i)}
                  onClick={() => choose(opt)}
                  className={`px-3 py-2 cursor-pointer text-sm flex items-center justify-between gap-2 ${
                    i === activeIdx ? 'bg-bg-elevated' : ''
                  } ${opt.value === value ? 'text-accent-neon font-medium' : 'text-text-primary'}`}
                >
                  <span className="truncate">{opt.label}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
