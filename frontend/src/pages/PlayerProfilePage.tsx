import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Settings, ExternalLink, Trophy, MapPin, Calendar, User,
  Link as LinkIcon, Loader2, ChevronRight, Ticket,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { PlayerProfile, TournamentRegistration } from '../types';
import { listProfiles } from '../services/data';
import { myRegistrations } from '../services/registrations';
import { mediaUrl } from '../services/api';
import { LEVEL_LABELS, GENDER_LABELS, ROLE_LABELS, TENNIS_CLASS_LABELS } from '../utils/format';

const SOURCE_LABELS: Record<string, string> = {
  cbt: 'CBT – Confederação Brasileira de Tênis',
  fpt: 'FPT SP – Federação Paulista',
  fbt: 'FBT – Federação Baiana',
  fct: 'FCT – Federação Cearense',
  cosat: 'COSAT',
  itf: 'ITF',
  utr: 'UTR',
};

const MODALITY_LABELS: Record<string, string> = {
  tennis: 'Tênis',
  beach_tennis: 'Beach Tennis',
  padel: 'Padel',
  wheelchair: 'Tênis em cadeira de rodas',
};

const REG_STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  confirmed: { label: 'Confirmado', cls: 'text-green-400 bg-green-400/10' },
  waiting_list: { label: 'Lista de espera', cls: 'text-yellow-400 bg-yellow-400/10' },
  pending_payment: { label: 'Pag. pendente', cls: 'text-orange-400 bg-orange-400/10' },
  withdrawn: { label: 'Desistiu', cls: 'text-red-400 bg-red-400/10' },
};

function extractTiId(value: unknown): string | null {
  if (!value) return null;
  const s = String(value);
  const m = s.match(/^tenisintegrado:(\d+)$/) || (!s.includes(':') && s.match(/^(\d+)$/));
  return m ? m[1] : null;
}

export const PlayerProfilePage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<PlayerProfile[]>([]);
  const [registrations, setRegistrations] = useState<TournamentRegistration[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listProfiles().catch(() => [] as PlayerProfile[]),
      myRegistrations().catch(() => [] as TournamentRegistration[]),
    ]).then(([profs, regs]) => {
      setProfiles(profs);
      setRegistrations(regs);
    }).finally(() => setLoading(false));
  }, []);

  const primary = profiles.find((p) => p.is_primary) ?? profiles[0] ?? null;
  const avatarLetter = (user?.full_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role ?? ''] ?? user?.role ?? '';

  // Tênis Integrado linked IDs from external_ids
  const tiLinks: { source: string; tiId: string }[] = [];
  if (primary?.external_ids) {
    for (const [src, val] of Object.entries(primary.external_ids)) {
      const tiId = extractTiId(val);
      if (tiId) tiLinks.push({ source: src, tiId });
    }
  }

  const activeRegs = registrations
    .filter((r) => !r.is_withdrawn && ['confirmed', 'waiting_list', 'pending_payment'].includes(r.registration_status))
    .slice(0, 5);

  return (
    <div className="space-y-4 pb-6">

      {/* ── Cabeçalho ───────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Perfil</h1>
        <Link
          to="/configuracoes"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent-neon/40 transition-colors text-xs font-medium"
          title="Configurações"
        >
          <Settings className="w-4 h-4" />
          <span className="hidden sm:inline">Configurações</span>
        </Link>
      </div>

      {/* ── User card ───────────────────────────────────────────────── */}
      <div className="card flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-accent-neon/20 flex items-center justify-center text-xl font-bold overflow-hidden border-2 border-accent-neon/40 shrink-0">
          {user?.avatar
            ? <img src={mediaUrl(user.avatar)} alt="avatar" className="w-full h-full object-cover" />
            : <span className="text-accent-neon text-2xl font-bold">{avatarLetter}</span>}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-bold text-lg leading-tight">{user?.full_name || '—'}</h2>
          <p className="text-xs text-text-muted mt-0.5 truncate">{user?.email}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-blue/15 text-accent-blue border border-accent-blue/25">
              {roleLabel}
            </span>
            {primary && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-accent-neon/12 text-accent-neon border border-accent-neon/25">
                {LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level}
              </span>
            )}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
      ) : (
        <>
          {/* ── Sem perfil ───────────────────────────────────────────── */}
          {!primary ? (
            <div className="card text-center py-8 space-y-3">
              <User className="w-10 h-10 text-text-muted mx-auto" />
              <p className="font-semibold text-sm">Perfil esportivo não configurado</p>
              <p className="text-xs text-text-muted">Complete seu perfil para ver torneios compatíveis.</p>
              <button className="btn-primary !text-sm" onClick={() => navigate('/onboarding')}>
                Completar perfil
              </button>
            </div>
          ) : (
            <>
              {/* ── Perfil esportivo ─────────────────────────────────── */}
              <section>
                <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Perfil esportivo</h3>
                <div className="card space-y-2.5">
                  {primary.display_name && (
                    <InfoRow icon={<User className="w-3.5 h-3.5" />} label="Atleta" value={primary.display_name} />
                  )}
                  <InfoRow icon={<Trophy className="w-3.5 h-3.5" />} label="Nível" value={LEVEL_LABELS[primary.competitive_level] ?? primary.competitive_level} />
                  {primary.tennis_class && (
                    <InfoRow icon={<Trophy className="w-3.5 h-3.5" />} label="Classe" value={TENNIS_CLASS_LABELS[primary.tennis_class] ?? primary.tennis_class} />
                  )}
                  {primary.preferred_modality && (
                    <InfoRow icon={<span className="text-[10px]">🎾</span>} label="Modalidade" value={MODALITY_LABELS[primary.preferred_modality] ?? primary.preferred_modality} />
                  )}
                  {primary.gender && (
                    <InfoRow icon={<User className="w-3.5 h-3.5" />} label="Gênero" value={GENDER_LABELS[primary.gender] ?? primary.gender} />
                  )}
                  {primary.birth_year && (
                    <InfoRow icon={<Calendar className="w-3.5 h-3.5" />} label="Nascimento" value={String(primary.birth_year)} />
                  )}
                  {primary.sporting_age != null && (
                    <InfoRow icon={<Calendar className="w-3.5 h-3.5" />} label="Idade esportiva" value={`${primary.sporting_age} anos`} />
                  )}
                  {(primary.home_city || primary.home_state) && (
                    <InfoRow icon={<MapPin className="w-3.5 h-3.5" />} label="Local" value={[primary.home_city, primary.home_state].filter(Boolean).join(' / ')} />
                  )}
                </div>
              </section>

              {/* ── Categorias ──────────────────────────────────────── */}
              {primary.categories?.length > 0 && (
                <section>
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Categorias compatíveis</h3>
                  <div className="card space-y-2">
                    {primary.categories.slice(0, 8).map((cat) => (
                      <div key={cat.id} className="flex items-center gap-2 text-xs">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cat.is_primary ? 'bg-accent-neon' : 'bg-text-muted'}`} />
                        <span className="flex-1">{cat.category_detail?.label_ptbr ?? cat.category_detail?.code ?? `Cat. ${cat.category}`}</span>
                        {cat.is_primary && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-neon/12 text-accent-neon font-medium">Principal</span>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* ── Vínculos Tênis Integrado ─────────────────────────── */}
              {tiLinks.length > 0 && (
                <section>
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">Vínculos externos</h3>
                  <div className="card divide-y divide-border-subtle">
                    {tiLinks.map(({ source, tiId }) => (
                      <a
                        key={source}
                        href={`https://www.tenisintegrado.com.br/perfil2/index/${tiId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-3 py-3 first:pt-0 last:pb-0 group"
                      >
                        <div className="w-8 h-8 rounded-lg bg-accent-blue/15 flex items-center justify-center shrink-0">
                          <LinkIcon className="w-4 h-4 text-accent-blue" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium leading-tight">{SOURCE_LABELS[source] ?? source.toUpperCase()}</p>
                          <p className="text-xs text-text-muted mt-0.5">ID: {tiId} · Tênis Integrado</p>
                        </div>
                        <ExternalLink className="w-4 h-4 text-text-muted group-hover:text-accent-blue transition-colors shrink-0" />
                      </a>
                    ))}
                    <p className="text-[10px] text-text-muted pt-3">
                      Clique para visualizar seu perfil na plataforma de origem.
                    </p>
                  </div>
                </section>
              )}
            </>
          )}

          {/* ── Inscrições ativas ───────────────────────────────────── */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wide">Inscrições ativas</h3>
              <Link to="/inscricoes" className="text-xs text-accent-blue hover:underline flex items-center gap-0.5">
                Ver todas <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            {activeRegs.length === 0 ? (
              <div className="card text-center py-6 space-y-2">
                <Ticket className="w-8 h-8 text-text-muted mx-auto" />
                <p className="text-xs text-text-muted">Nenhuma inscrição ativa encontrada.</p>
                <Link to="/torneios" className="text-xs text-accent-neon hover:underline">Ver torneios disponíveis</Link>
              </div>
            ) : (
              <div className="card divide-y divide-border-subtle">
                {activeRegs.map((reg) => {
                  const st = REG_STATUS_LABELS[reg.registration_status] ?? { label: reg.registration_status, cls: 'text-text-muted bg-text-muted/10' };
                  return (
                    <div key={reg.id} className="py-3 first:pt-0 last:pb-0 space-y-1">
                      <p className="text-sm font-semibold leading-tight line-clamp-2">{reg.edition_title}</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        {reg.category_text && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-neon/10 text-accent-neon">{reg.category_text}</span>
                        )}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${st.cls}`}>{st.label}</span>
                      </div>
                      {reg.edition_start_date && (
                        <p className="text-xs text-text-muted">
                          {new Date(reg.edition_start_date).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-text-muted shrink-0 w-4 flex justify-center">{icon}</span>
      <span className="text-text-muted w-28 shrink-0 text-xs">{label}</span>
      <span className="font-medium truncate">{value}</span>
    </div>
  );
}
