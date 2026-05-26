import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import { TournamentEditionDetail } from '../types';
import { getEdition, checkConflicts, ConflictPair } from '../services/tournaments';
import { fmtDate, fmtDateRange, fmtBRL, STATUS_LABELS } from '../utils/format';

const FIELD_ROWS: {
  key: string;
  label: string;
  render: (d: TournamentEditionDetail) => string;
}[] = [
  { key: 'status',    label: 'Status',                render: (d) => (STATUS_LABELS as Record<string, string>)[d.dynamic_status ?? d.status ?? ''] ?? d.status },
  { key: 'dates',     label: 'Datas',                 render: (d) => fmtDateRange(d.start_date, d.end_date) },
  { key: 'deadline',  label: 'Prazo de inscrição',    render: (d) => fmtDate(d.entry_close_at) },
  { key: 'location',  label: 'Local',                 render: (d) => d.venue_city && d.venue_state ? `${d.venue_city} – ${d.venue_state}` : d.venue_name ?? '—' },
  { key: 'price',     label: 'Valor',                 render: (d) => d.base_price_brl ? fmtBRL(d.base_price_brl) : '—' },
  { key: 'categories',label: 'Categorias',            render: (d) => String(d.categories?.length ?? 0) },
  { key: 'circuit',   label: 'Circuito',              render: (d) => d.circuit || d.organization_short || '—' },
  { key: 'surface',   label: 'Quadra',                render: (d) => d.surface || '—' },
  { key: 'confidence',label: 'Qualidade dos dados',   render: (d) => ({ low: 'Baixa', med: 'Média', medium: 'Média', high: 'Alta' }[d.data_confidence] ?? '—') },
];

export const TournamentComparePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const rawIds = searchParams.get('ids') ?? '';
  const ids = rawIds.split(',').map(Number).filter(Boolean);

  const [details, setDetails] = useState<(TournamentEditionDetail | null)[]>([]);
  const [conflicts, setConflicts] = useState<ConflictPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ids.length < 2) {
      setError('Selecione pelo menos 2 torneios para comparar.');
      setLoading(false);
      return;
    }
    Promise.all([
      Promise.all(ids.map((id) => getEdition(id).catch(() => null))),
      checkConflicts(ids).catch(() => ({ conflicts: [], has_conflicts: false })),
    ])
      .then(([detailResults, conflictResult]) => {
        setDetails(detailResults);
        setConflicts(conflictResult.conflicts);
      })
      .catch(() => setError('Não foi possível carregar os torneios para comparação.'))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawIds]);

  const loaded = details.filter(Boolean) as TournamentEditionDetail[];

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  if (error || loaded.length === 0) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="btn-ghost flex items-center gap-2 text-sm">
          <ArrowLeft className="w-4 h-4" /> Voltar
        </button>
        <div className="card text-center py-10 space-y-2">
          <p className="font-semibold">{error ?? 'Nenhum torneio encontrado.'}</p>
          <Link to="/torneios" className="btn-primary inline-flex items-center gap-1 text-sm">
            Ver torneios
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-ghost !p-2">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-xl font-bold">Comparar torneios</h1>
          <p className="text-xs text-text-muted">{loaded.length} torneios selecionados</p>
        </div>
      </div>

      {/* Conflict warning */}
      {conflicts.length > 0 && (
        <div className="flex items-start gap-3 bg-status-closing/10 border border-status-closing/30 rounded-xl px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-status-closing mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-status-closing">Conflito de datas detectado</p>
            {conflicts.map((c, i) => (
              <p key={i} className="text-xs text-text-secondary mt-0.5">
                "{c.edition_a.title}" e "{c.edition_b.title}" têm datas sobrepostas.
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Comparison table — scrollable horizontally on small screens */}
      <div className="overflow-x-auto rounded-xl border border-border-subtle">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="bg-bg-elevated border-b border-border-subtle">
              <th className="text-left text-xs text-text-muted font-semibold px-4 py-3 w-32 shrink-0">Campo</th>
              {loaded.map((d) => (
                <th key={d.id} className="text-left px-4 py-3 border-l border-border-subtle min-w-[180px]">
                  <Link
                    to={`/torneios/${d.id}`}
                    className="font-bold text-sm hover:text-accent-neon transition-colors line-clamp-2 block"
                  >
                    {d.title}
                  </Link>
                  <span className="text-[11px] text-text-muted block mt-0.5">{d.organization_name}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FIELD_ROWS.map((row, idx) => (
              <tr
                key={row.key}
                className={`border-b border-border-subtle ${idx % 2 === 0 ? 'bg-bg-base' : 'bg-bg-subtle'}`}
              >
                <td className="text-xs text-text-muted px-4 py-2.5 font-medium">{row.label}</td>
                {loaded.map((d) => (
                  <td key={d.id} className="px-4 py-2.5 border-l border-border-subtle text-sm">
                    {row.render(d)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Categories breakdown */}
      <div className="card space-y-3">
        <h2 className="font-semibold text-sm">Categorias</h2>
        <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${loaded.length}, minmax(0, 1fr))` }}>
          {loaded.map((d) => (
            <div key={d.id}>
              <p className="text-xs text-text-muted font-semibold mb-1 truncate">{d.title}</p>
              {d.categories?.length ? (
                <div className="space-y-1">
                  {d.categories.map((c) => (
                    <div key={c.id} className="text-xs text-text-secondary">
                      • {c.source_category_text}
                      {c.price_brl && (
                        <span className="text-text-muted ml-1">({fmtBRL(c.price_brl)})</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-text-muted">—</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Official links */}
      <div className="card space-y-3">
        <h2 className="font-semibold text-sm">Links oficiais</h2>
        <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${loaded.length}, minmax(0, 1fr))` }}>
          {loaded.map((d) => (
            <div key={d.id}>
              <p className="text-xs text-text-muted font-semibold mb-1 truncate">{d.title}</p>
              {d.official_source_url ? (
                <a
                  href={d.official_source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-accent-neon hover:underline"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Abrir fonte oficial
                </a>
              ) : (
                <span className="text-xs text-text-muted">Não disponível</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Individual detail links */}
      <div className="flex flex-wrap gap-2">
        {loaded.map((d) => (
          <Link
            key={d.id}
            to={`/torneios/${d.id}`}
            className="btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5"
          >
            {d.title}
          </Link>
        ))}
      </div>
    </div>
  );
};
