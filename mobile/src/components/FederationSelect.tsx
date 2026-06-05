import React, { useEffect, useMemo, useState } from 'react';
import { SelectField } from './ui';
import { Organization } from '../types';
import { listAllFederations } from '../services/tournaments';

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
export function FederationSelect({
  label = 'Por qual federação você joga?',
  value,
  onChange,
  required,
}: Props) {
  const [federations, setFederations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    listAllFederations()
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
    <SelectField
      label={label}
      value={value != null ? String(value) : ''}
      options={options}
      onSelect={(v) => onChange(v ? Number(v) : null)}
      placeholder="Selecione a federação"
      loading={loading}
      searchable
      required={required}
    />
  );
}
