import React, { useEffect, useMemo, useState } from 'react';
import { Federation } from '../types';
import { listFederations } from '../services/data';
import { SearchableSelect } from './SearchableSelect';

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

  const options = useMemo(
    () => federations.map((f) => ({
      value: String(f.id),
      label: `${f.name}${f.state ? ` (${f.state})` : ''}`,
    })),
    [federations],
  );

  return (
    <SearchableSelect
      label={label ? `${label}${required ? ' *' : ''}` : undefined}
      value={value != null ? String(value) : ''}
      onChange={(v) => onChange(v ? Number(v) : null)}
      options={options}
      placeholder={loading ? 'Carregando federações...' : 'Selecione a federação'}
      disabled={loading}
      allowClear={!required}
    />
  );
};
