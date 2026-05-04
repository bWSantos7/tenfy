import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft, Calendar, MapPin, Clock, ExternalLink, Star, CheckCircle2,
  XCircle, HelpCircle, Loader2, AlertTriangle, FileText, History, Share2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { TournamentEditionDetail, EditionEligibility, PlayerProfile } from '../types';
import { getEdition, evaluateEdition } from '../services/tournaments';
import { listProfiles, toggleWatchlist, listWatchlist } from '../services/data';
import {
  STATUS_LABELS, fmtDateRange, fmtDateTime, fmtBRL, fmtRelative,
  statusBgClass, translateReason, formatChangeEventTitle, formatChangeEventDetails,
} from '../utils/format';
import { extractApiError } from '../services/api';
import { pickBestProfile } from '../utils/profile';

export const TournamentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [ed, setEd] = useState<TournamentEditionDetail | null>(null);
  const [elig, setElig] = useState<EditionEligibility | null>(null);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [watching, setWatching] = useState(false);
  const [watchingItemId, setWatchingItemId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [togglingWatch, setTogglingWatch] = useState(false);

  async function handleShare() {
    const url = window.location.href;
    const title = ed?.title ?? 'Torneio';
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
      } catch {
        // user cancelled
      }
    } else {
      await navigator.clipboard.writeText(url);
      toast.success('Link copiado!');
    }
  }

  useEffect(() => {
    if (!id) return;
    const edId = Number(id);
    (async () => {
      setLoading(true);
      try {
        const [edition, profiles, watchlist] = await Promise.all([
          getEdition(edId),
          listProfiles().catch(() => []),
          listWatchlist().catch(() => []),
        ]);
        setEd(edition);
        const primary = pickBestProfile(profiles);
        setProfile(primary);
        const watchItem = watchlist.find((w) => w.edition === edId);
        setWatching(!!watchItem);
        setWatchingItemId(watchItem?.id ?? null);
        if (primary) {
          try {
            const e = await evaluateEdition(edId, primary.id);
            setElig(e);
          } catch {
            // Ignore eligibility errors and keep the rest of the page usable.
          }
        }
      } catch (err) {
        toast.error(extractApiError(err));
        nav('/torneios');
      } finally {
        setLoading(false);
      }
    })();
  }, [id, nav]);

  async function handleWatch() {
    if (!ed) return;
    setTogglingWatch(true);
    try {
      const r = await toggleWatchlist(ed.id, profile?.id);
      setWatching(r.watching);
      setWatchingItemId(r.item?.id ?? null);
      toast.success(r.watching ? 'Adicionado à sua agenda' : 'Removido da agenda');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setTogglingWatch(false);
    }
  }

  if (loading || !ed) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  const status = ed.dynamic_status || ed.status;
  const statusLabel = STATUS_LABELS[status];
  const location = [
    ed.venue_detail?.name && ed.venue_detail.name !== 'CBT' ? ed.venue_detail.name : null,
    [ed.venue_city, ed.venue_state].filter(Boolean).join('/'),
  ].filter(Boolean).join(' • ');
  const regLink = ed.links.find((l) => l.link_type === 'registration') || null;
  const regURL = regLink?.url || ed.official_source_url;
  const regulation = ed.links.find((l) => l.link_type === 'regulation') || null;

  const compatCats = (elig?.categories || []).filter((c) => c.result.status === 'compatible');
  const unknownCats = (elig?.categories || []).filter((c) => c.result.status === 'unknown');
  const incompatCats = (elig?.categories || []).filter((c) => c.result.status === 'incompatible');

  return (
    <div className="space-y-4 pb-4">
      <button onClick={() => nav(-1)} className="btn-ghost flex items-center gap-1 -ml-2">
        <ArrowLeft className="w-4 h-4" /> Voltar
      </button>

      <div className="card space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold text-accent-blue uppercase tracking-wider">
              {ed.tournament_detail.organization_detail.short_name ||
                ed.tournament_detail.organization_detail.name}
              {ed.tournament_detail.circuit && ` • ${ed.tournament_detail.circuit}`}
            </div>
            <h1 className="text-xl font-bold leading-tight mt-1">{ed.title}</h1>
          </div>
          <div className={`badge border ${statusBgClass(status)} shrink-0`}>
            {statusLabel}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm pt-2">
          <Stat
            icon={<Calendar className="w-4 h-4" />}
            label="Período"
            value={fmtDateRange(ed.start_date, ed.end_date)}
          />
          <Stat
            icon={<MapPin className="w-4 h-4" />}
            label="Local"
            value={location || '—'}
          />
          <Stat
            icon={<Clock className="w-4 h-4" />}
            label="Prazo de inscrição"
            value={ed.entry_close_at ? fmtDateTime(ed.entry_close_at) : '—'}
            accent={!!ed.entry_close_at}
          />
          <Stat
            icon={<FileText className="w-4 h-4" />}
            label="Valor base"
            value={fmtBRL(ed.base_price_brl)}
          />
        </div>

        {ed.venue_detail?.address && (
          <div className="text-xs text-text-secondary pt-1">
            Endereço: {ed.venue_detail.address}
          </div>
        )}

        {ed.is_manual_override && (
          <div className="flex items-start gap-2 text-xs bg-accent-blue/10 border border-accent-blue/30 rounded-lg p-2">
            <AlertTriangle className="w-4 h-4 text-accent-blue shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-accent-blue">Dados validados manualmente</div>
              <div className="text-text-secondary">
                {ed.reviewed_by_email && `Revisado por ${ed.reviewed_by_email}. `}
                Alterações automáticas suspensas para este torneio.
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 pt-1">
          {regURL && (
            <a
              href={regURL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary flex items-center justify-center gap-2"
            >
              <ExternalLink className="w-4 h-4" /> Inscrição oficial
            </a>
          )}
          <button
            className={`btn-secondary flex items-center justify-center gap-2 ${
              watching ? '!border-accent-neon !text-accent-neon' : ''
            }`}
            onClick={handleWatch}
            disabled={togglingWatch}
          >
            {togglingWatch
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Star className={`w-4 h-4 ${watching ? 'fill-accent-neon' : ''}`} />}
            {watching ? 'Na sua agenda' : 'Acompanhar'}
          </button>
        </div>
        <button
          onClick={handleShare}
          className="w-full btn-ghost flex items-center justify-center gap-2 text-sm border border-border-subtle rounded-xl py-2"
        >
          <Share2 className="w-4 h-4" /> Compartilhar torneio
        </button>

        {regulation && (
          <a
            href={regulation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-accent-blue hover:underline inline-flex items-center gap-1"
          >
            <FileText className="w-3 h-3" /> Regulamento oficial
          </a>
        )}
      </div>

      <div className="card">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          Categorias
          {elig && (
            <span className="text-xs text-text-muted font-normal">
              {elig.total_count} no total — {elig.compatible_count} compatíveis com você
            </span>
          )}
        </h2>

        {(!elig || elig.total_count === 0) && ed.categories.length > 0 && (
          <div className="space-y-2">
            {ed.categories.map((c) => (
              <div key={c.id} className="flex items-center justify-between text-sm">
                <span>{c.source_category_text}</span>
                {c.price_brl && <span className="text-text-muted">{fmtBRL(c.price_brl)}</span>}
              </div>
            ))}
            {!profile && (
              <p className="text-xs text-text-muted pt-2">
                <Link to="/perfil" className="text-accent-neon hover:underline">
                  Configure seu perfil
                </Link>{' '}
                para ver quais categorias são compatíveis com você.
              </p>
            )}
          </div>
        )}

        {elig && elig.total_count > 0 && (
          <div className="space-y-3">
            {compatCats.length > 0 && (
              <CategoryGroup
                title="Compatíveis com você"
                color="text-accent-neon"
                icon={<CheckCircle2 className="w-4 h-4" />}
                items={compatCats}
              />
            )}
            {unknownCats.length > 0 && (
              <CategoryGroup
                title="Indeterminadas"
                color="text-text-secondary"
                icon={<HelpCircle className="w-4 h-4" />}
                items={unknownCats}
                subdued
              />
            )}
            {incompatCats.length > 0 && (
              <CategoryGroup
                title="Outras categorias"
                color="text-text-muted"
                icon={<XCircle className="w-4 h-4" />}
                items={incompatCats}
                subdued
              />
            )}
          </div>
        )}

        {ed.categories.length === 0 && (
          <p className="text-sm text-text-muted">
            Nenhuma categoria listada pela fonte. Consulte o regulamento oficial.
          </p>
        )}
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2 flex items-center gap-2">
          <FileText className="w-4 h-4" /> Origem dos dados
        </h2>
        <dl className="text-xs space-y-1 text-text-secondary">
          <div className="flex justify-between">
            <dt>Fonte</dt>
            <dd className="text-text-primary">{ed.source_name || '—'}</dd>
          </div>
          {ed.official_source_url && (
            <div className="flex justify-between items-center">
              <dt>Link oficial</dt>
              <dd>
                <a
                  href={ed.official_source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent-blue hover:underline truncate max-w-[180px] inline-block"
                >
                  {new URL(ed.official_source_url).hostname}
                </a>
              </dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt>Última atualização</dt>
            <dd className="text-text-primary">{ed.fetched_at ? fmtRelative(ed.fetched_at) : '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Confiança dos dados</dt>
            <dd
              className={`font-medium ${
                ed.data_confidence === 'high' ? 'text-accent-neon'
                : ed.data_confidence === 'low' ? 'text-status-canceled'
                : 'text-status-closing'
              }`}
            >
              {ed.data_confidence === 'high' ? 'Alta'
                : ed.data_confidence === 'low' ? 'Baixa' : 'Média'}
            </dd>
          </div>
        </dl>
      </div>

      {ed.change_events && ed.change_events.length > 0 && (
        <div className="card">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <History className="w-4 h-4" /> Histórico de alterações
          </h2>
          <ol className="space-y-2 text-xs">
            {ed.change_events.slice(0, 8).map((e) => (
              <li key={e.id} className="border-l-2 border-border-subtle pl-3 py-1">
                <div className="text-text-primary font-medium">{formatChangeEventTitle(e.event_type)}</div>
                <div className="text-text-muted">{fmtRelative(e.detected_at)}</div>
                <div className="text-[11px] text-text-secondary mt-1 space-y-1">
                  {formatChangeEventDetails(e).map((line) => (
                    <div key={`${e.id}-${line}`}>{line}</div>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string;
  accent?: boolean;
}> = ({ icon, label, value, accent = false }) => (
  <div>
    <div className="text-[10px] text-text-muted uppercase tracking-wider flex items-center gap-1">
      {icon} {label}
    </div>
    <div className={`text-sm mt-0.5 font-medium ${accent ? 'text-accent-neon' : ''}`}>
      {value}
    </div>
  </div>
);

const CategoryGroup: React.FC<{
  title: string;
  color: string;
  icon: React.ReactNode;
  items: EditionEligibility['categories'];
  subdued?: boolean;
}> = ({ title, color, icon, items, subdued = false }) => (
  <div>
    <div className={`text-xs font-semibold mb-2 flex items-center gap-1 ${color}`}>
      {icon} {title} ({items.length})
    </div>
    <div className="space-y-1">
      {items.map((c) => (
        <div
          key={c.tournament_category_id}
          className={`flex items-start justify-between gap-2 p-2 rounded-lg ${
            subdued ? 'bg-bg-subtle/40' : 'bg-accent-neon/5 border border-accent-neon/20'
          }`}
        >
          <div className="min-w-0">
            <div className={`text-sm font-medium ${subdued ? 'text-text-secondary' : 'text-text-primary'}`}>
              {c.source_text}
            </div>
            {c.result.reasons.length > 0 && (
              <div className="text-[10px] text-text-muted mt-0.5">
                {c.result.reasons.map((r) => translateReason(r)).join(' • ')}
              </div>
            )}
            {c.result.ranking_check && c.result.ranking_check !== 'not_applicable' && (
              <div
                className={`text-[10px] mt-0.5 ${
                  c.result.ranking_check === 'within_cutoff'
                    ? 'text-accent-neon'
                    : c.result.ranking_check === 'beyond_cutoff'
                    ? 'text-amber-400'
                    : 'text-text-muted italic'
                }`}
              >
                {c.result.ranking_check === 'within_cutoff' && '✓ Ranking dentro do corte estimado.'}
                {c.result.ranking_check === 'beyond_cutoff' && '⚠ Ranking acima do corte estimado — vaga incerta. Confirme na fonte oficial.'}
                {c.result.ranking_check === 'unknown' && (c.result.ranking_note || 'Corte de ranking não estimado.')}
              </div>
            )}
          </div>
          {c.price_brl && (
            <span className="text-xs text-text-muted whitespace-nowrap">{fmtBRL(c.price_brl)}</span>
          )}
        </div>
      ))}
    </div>
  </div>
);
