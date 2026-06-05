import React, { useEffect, useState } from 'react';
import { Federation } from '../types';
import { listFederations } from '../services/data';

interface Props {
  label?: string;
  value: number | null;
  onChange: (federationId: number | null) => void;
  required?: boolean;
}

/**
 * Single-select federation picker — replaces the legacy multi-state selector.
 * The player competes for exactly one federation; its UF drives eligibility.
 */
export const FederationSelect: React.FC<Props> = ({
  label = 'Por qual federação você joga?',
  value,
  onChange,
  required = false,
}) => {
  const [federations, setFederations] = useState<Federation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    listFederations()
      .then((data) => { if (active) setFederations(data); })
      .catch(() => { if (active) setFederations([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <div>
      {label && (
        <label className="text-xs text-text-secondary mb-1 block">
          {label}{required && ' *'}
        </label>
      )}
      <select
        className="input-base"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        disabled={loading}
      >
        <option value="">{loading ? 'Carregando federações...' : 'Selecione a federação'}</option>
        {federations.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}{f.state ? ` (${f.state})` : ''}
          </option>
        ))}
      </select>
    </div>
  );
};
