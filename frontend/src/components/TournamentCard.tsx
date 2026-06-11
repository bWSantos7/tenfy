import React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Calendar, Clock, Circle, CheckCircle2, Receipt, Info } from 'lucide-react';
import { TournamentEditionList } from '../types';
import { STATUS_LABELS, fmtBRL, fmtDateRange, fmtRelative, fmtDateTime, statusBgClass } from '../utils/format';
import { editionCountry } from '../utils/country';
import { orgLogoUrl } from '../utils/orgLogos';

import logoFPT from '../assets/logos/FPT.jpg';
import logoCBT from '../assets/logos/CBT.jpg';
import logoCOSAT from '../assets/logos/COSAT.jpg';
import logoFCT from '../assets/logos/FCT.webp';
import logoITF from '../assets/logos/ITF.jpg';

const LOCAL_ORG_LOGOS: Record<string, string> = {
  FPT:   logoFPT,
  CBT:   logoCBT,
  COSAT: logoCOSAT,
  FCT:   logoFCT,
  ITF:   logoITF,
  UTR:   '/logo_federacao/utr.png',  // served from public/
};

function findLocalLogo(edition: TournamentEditionList): string | null {
  for (const c of [edition.organization_short || '', edition.organization_name || '']) {
    const upper = c.toUpperCase().trim();
    if (LOCAL_ORG_LOGOS[upper]) return LOCAL_ORG_LOGOS[upper];
    const first = upper.split(/[\s/(-]/)[0];
    if (LOCAL_ORG_LOGOS[first]) return LOCAL_ORG_LOGOS[first];
    for (const key of Object.keys(LOCAL_ORG_LOGOS)) {
      if (upper.includes(key)) return LOCAL_ORG_LOGOS[key];
    }
  }
  return null;
}

function resolveOrgLogo(edition: TournamentEditionList): string | null {
  // 1) logos oficiais por federação/conector (public/logo_federacao, todas as UFs)
  // 2) assets embutidos (ITF etc.) 3) URL vinda do backend.
  return orgLogoUrl(edition.organization_name, edition.organization_short)
    ?? findLocalLogo(edition)
    ?? edition.organization_logo_url ?? null;
}

interface Props {
  edition: TournamentEditionList;
  showEligibility?: boolean;
  variant?: 'list' | 'calendar';
}

export const TournamentCard: React.FC<Props> = ({
  edition,
  showEligibility = false,
  variant = 'list',
}) => {
  const status = edition.dynamic_status || edition.status;
  const statusLabel = STATUS_LABELS[status] || status;
  const statusCls = statusBgClass(status);
  // International sources (UTR/ITF/COSAT) carry a country; show flag + country
  // name instead of the BR-style "city / UF" (where UF is actually a country code).
  const country = editionCountry({
    venue_country: edition.venue_country,
    venue_country_code: edition.venue_country_code,
  });
  const location = country
    ? [edition.venue_city, country.name].filter(Boolean).join(', ')
    : [edition.venue_city, edition.venue_state].filter(Boolean).join(' / ');
  const flagUrl = country?.flagUrl || '';
  const orgLogo = resolveOrgLogo(edition);

  if (variant === 'calendar') {
    return (
      <Link
        to={`/torneios/${edition.id}`}
        className="card hover:border-accent-neon/50 transition-colors flex flex-col gap-3 h-full active:scale-[0.99]"
        data-testid="tournament-card"
        data-modality={edition.modality || ''}
        data-venue-state={edition.venue_state || ''}
      >
        {/* Logo + org */}
        <div className="flex flex-col items-center gap-1.5">
          <div className="w-12 h-12 rounded-full overflow-hidden bg-white flex items-center justify-center shrink-0 border border-border-subtle">
            {orgLogo ? (
              <img
                src={orgLogo}
                alt={edition.organization_short || edition.organization_name}
                className="w-full h-full object-contain p-0.5"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  e.currentTarget.nextElementSibling?.removeAttribute('hidden');
                }}
              />
            ) : null}
            <span
              hidden={!!orgLogo}
              className="text-accent-blue font-bold text-sm"
            >
              {(edition.organization_short || edition.organization_name || '?').slice(0, 2).toUpperCase()}
            </span>
          </div>
          <span className="text-[10px] font-semibold text-accent-blue uppercase tracking-wider text-center leading-tight">
            {edition.organization_short || edition.organization_name}
          </span>
        </div>

        {/* Title */}
        <h3 className="font-bold text-sm text-text-primary leading-snug line-clamp-3 text-center flex-1">
          {edition.title}
        </h3>

        {/* Info rows */}
        <div className="space-y-2 text-xs text-text-secondary">
          {(edition.entry_open_at || edition.entry_close_at) && (
            <div>
              <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-0.5">
                Período Inscrições
              </p>
              <p>
                {edition.entry_open_at && edition.entry_close_at
                  ? `${fmtDateTime(edition.entry_open_at)} a ${fmtDateTime(edition.entry_close_at)}`
                  : edition.entry_close_at
                    ? `Até ${fmtDateTime(edition.entry_close_at)}`
                    : `A partir de ${fmtDateTime(edition.entry_open_at)}`}
              </p>
            </div>
          )}
          <div>
            <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-0.5">
              Período Torneio
            </p>
            <p>{fmtDateRange(edition.start_date, edition.end_date)}</p>
          </div>
          {location && (
            <span className="flex items-center gap-1 text-text-secondary">
              {flagUrl
                ? <img src={flagUrl} alt="" className="w-4 h-3 rounded-[2px] object-cover shrink-0" />
                : <MapPin className="w-3.5 h-3.5 shrink-0" />}
              {location}
            </span>
          )}
          {edition.base_price_brl !== null && edition.base_price_brl !== undefined && (
            <span className="flex items-center gap-1">
              <Receipt className="w-3.5 h-3.5 shrink-0" />
              Inscrição {fmtBRL(edition.base_price_brl)}
            </span>
          )}
        </div>

        {/* Status + eligibility */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border-subtle">
          <span className={`badge border ${statusCls}`}>{statusLabel}</span>
          {edition.entry_close_at && (status === 'closing_soon') && (
            <span className="text-[10px] text-status-closing font-medium">
              Prazo {fmtRelative(edition.entry_close_at)}
            </span>
          )}
          {showEligibility && edition.eligibility && edition.eligibility.entry_model === 'acceptance_list' && (
            <span
              className="flex items-center gap-1 text-amber-400 text-[10px] font-medium"
              title={edition.eligibility.distance_message || 'Inscrição sujeita à aceitação'}
            >
              <Info className="w-3.5 h-3.5" />
              Sujeito à aceitação
            </span>
          )}
          {showEligibility && edition.eligibility && edition.eligibility.compatible_count > 0 && (
            <span className="flex items-center gap-1 text-accent-neon text-[10px] font-medium ml-auto">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {edition.eligibility.compatible_count} compatíveis
            </span>
          )}
        </div>
      </Link>
    );
  }

  // variant === 'list' (default)
  return (
    <Link
      to={`/torneios/${edition.id}`}
      className="card hover:border-accent-neon/50 transition-colors active:scale-[0.99] block"
      data-testid="tournament-card"
      data-modality={edition.modality || ''}
      data-venue-state={edition.venue_state || ''}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            {orgLogo && (
              <img
                src={orgLogo}
                alt={edition.organization_short || edition.organization_name}
                className="w-4 h-4 object-contain rounded-sm shrink-0"
              />
            )}
            <span className="text-[10px] font-semibold text-accent-blue uppercase tracking-wider">
              {edition.organization_short || edition.organization_name}
            </span>
            {edition.circuit && (
              <span className="text-[10px] text-text-muted">• {edition.circuit}</span>
            )}
          </div>
          <h3 className="font-semibold text-text-primary leading-snug line-clamp-2 break-words">
            {edition.title}
          </h3>
        </div>
        <div className={`badge border ${statusCls} shrink-0`}>
          {statusLabel}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        <span className="flex items-center gap-1">
          <Calendar className="w-3.5 h-3.5" />
          {fmtDateRange(edition.start_date, edition.end_date)}
        </span>
        {location && (
          <span className="flex items-center gap-1">
            {flagUrl
              ? <img src={flagUrl} alt="" className="w-4 h-3 rounded-[2px] object-cover shrink-0" />
              : <MapPin className="w-3.5 h-3.5" />}
            {location}
          </span>
        )}
        {edition.entry_close_at && (
          <span className="flex items-center gap-1 text-status-closing">
            <Clock className="w-3.5 h-3.5" />
            Prazo {fmtRelative(edition.entry_close_at)}
          </span>
        )}
        {edition.base_price_brl !== null && edition.base_price_brl !== undefined && (
          <span className="flex items-center gap-1 text-text-primary">
            <Receipt className="w-3.5 h-3.5" />
            Inscrição {fmtBRL(edition.base_price_brl)}
          </span>
        )}
      </div>

      {showEligibility && edition.eligibility && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center gap-1 text-accent-neon font-medium">
            <CheckCircle2 className="w-4 h-4" />
            {edition.eligibility.compatible_count} compatíveis
          </span>
          {edition.eligibility.unknown_count > 0 && (
            <span className="flex items-center gap-1 text-text-muted">
              <Circle className="w-4 h-4" />
              {edition.eligibility.unknown_count} a verificar
            </span>
          )}
          {edition.eligibility.circuit_hint === 'cosat_ranking_required' && (
            <span className="text-text-muted italic">Requer ranking COSAT</span>
          )}
          {edition.eligibility.circuit_hint === 'itf_ranking_required' && (
            <span className="text-text-muted italic">Requer ranking ITF</span>
          )}
          {edition.eligibility.entry_model === 'acceptance_list' && (
            <span
              className="flex items-center gap-1 text-amber-400 font-medium"
              title={edition.eligibility.distance_message || undefined}
            >
              <Info className="w-4 h-4" />
              Inscrição sujeita à aceitação
            </span>
          )}
        </div>
      )}
    </Link>
  );
};
