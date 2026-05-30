import React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Calendar, Clock, Circle, CheckCircle2, Receipt } from 'lucide-react';
import { TournamentEditionList } from '../types';
import { STATUS_LABELS, fmtBRL, fmtDateRange, fmtRelative, fmtDateTime, statusBgClass } from '../utils/format';

const LOCAL_ORG_LOGOS: Record<string, string> = {
  FPT:   '/logo_federacao/FPT.jpg',
  CBT:   '/logo_federacao/CBT.jpg',
  COSAT: '/logo_federacao/COSAT.jpg',
  FCT:   '/logo_federacao/FCT.webp',
};

function resolveOrgLogo(edition: TournamentEditionList): string | null {
  if (edition.organization_logo_url) return edition.organization_logo_url;
  const candidates = [
    edition.organization_short || '',
    edition.organization_name || '',
  ];
  for (const c of candidates) {
    const upper = c.toUpperCase().trim();
    if (LOCAL_ORG_LOGOS[upper]) return LOCAL_ORG_LOGOS[upper];
    // try first word (e.g. "FPT SP" → "FPT")
    const first = upper.split(/[\s/(-]/)[0];
    if (LOCAL_ORG_LOGOS[first]) return LOCAL_ORG_LOGOS[first];
    // try any key that appears inside the string
    for (const key of Object.keys(LOCAL_ORG_LOGOS)) {
      if (upper.includes(key)) return LOCAL_ORG_LOGOS[key];
    }
  }
  return null;
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
  const location = [edition.venue_city, edition.venue_state].filter(Boolean).join(' / ');
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
              />
            ) : (
              <span className="text-accent-blue font-bold text-sm">
                {(edition.organization_short || edition.organization_name || '?').slice(0, 2).toUpperCase()}
              </span>
            )}
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
          {edition.entry_close_at && (
            <div>
              <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-0.5">
                Período Inscrições
              </p>
              <p>Até {fmtDateTime(edition.entry_close_at)}</p>
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
              <MapPin className="w-3.5 h-3.5 shrink-0" />
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
            <MapPin className="w-3.5 h-3.5" />
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
        </div>
      )}
    </Link>
  );
};
