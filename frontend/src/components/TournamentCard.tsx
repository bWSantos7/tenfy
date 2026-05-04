import React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Calendar, Clock, Circle, CheckCircle2, Receipt } from 'lucide-react';
import { TournamentEditionList } from '../types';
import { STATUS_LABELS, fmtBRL, fmtDateRange, fmtRelative, statusBgClass } from '../utils/format';

interface Props {
  edition: TournamentEditionList;
  showEligibility?: boolean;
}

export const TournamentCard: React.FC<Props> = ({ edition, showEligibility = false }) => {
  const status = edition.dynamic_status || edition.status;
  const statusLabel = STATUS_LABELS[status] || status;
  const statusCls = statusBgClass(status);
  const location = [edition.venue_city, edition.venue_state].filter(Boolean).join('/');

  return (
    <Link
      to={`/torneios/${edition.id}`}
      className="card hover:border-accent-neon/50 transition-colors active:scale-[0.99] block"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
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
        <div className="mt-3 flex items-center gap-3 text-xs">
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
        </div>
      )}
    </Link>
  );
};
