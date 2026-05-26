import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Clock, Sparkles, Bell, Loader2, CalendarDays, User, AlertTriangle } from 'lucide-react';
import { TournamentEditionList, PlayerProfile } from '../types';
import { closingSoon, compatibleForProfile, listEditions } from '../services/tournaments';
import { listChildren, listProfiles, unreadAlerts } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { useAuth } from '../contexts/AuthContext';
import { pickBestProfile } from '../utils/profile';
import { getActiveProfileId } from '../utils/activeProfile';
import { consumeProfileDirty } from '../utils/profileRefresh';
import { getProfileModality, syncModalityFromProfile } from '../utils/profileModality';

const ACTIVE_STATUSES = new Set(['open', 'closing_soon', 'announced', 'in_progress']);

export const HomePage: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [activeChildName, setActiveChildName] = useState<string | null>(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [compat, setCompat] = useState<TournamentEditionList[]>([]);
  const [closing, setClosing] = useState<TournamentEditionList[]>([]);
  const [recent, setRecent] = useState<TournamentEditionList[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [modalityMissing, setModalityMissing] = useState(false);
  const hasLoadedRef = useRef(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [closingData, recentData, alerts] = await Promise.all([
        closingSoon(14).catch(() => [] as TournamentEditionList[]),
        listEditions({ page_size: 8, ordering: '-created_at' }).catch(() => ({ results: [] as TournamentEditionList[] })),
        unreadAlerts().catch(() => [] as any[]),
      ]);

      setClosing((closingData as TournamentEditionList[]).filter((t) => ACTIVE_STATUSES.has(t.status ?? '')).slice(0, 6));
      setRecent(((recentData as any).results || []).slice(0, 6));
      setUnreadCount((alerts || []).length);

      // Parent users: use the stored active child profile
      let primary: PlayerProfile | null = null;
      let childName: string | null = null;

      if (user?.role === 'parent' && user.id) {
        const [profiles, children] = await Promise.all([
          listProfiles().catch(() => [] as PlayerProfile[]),
          listChildren().catch(() => []),
        ]);
        const activeId = getActiveProfileId(user.id);
        if (activeId) {
          primary = profiles.find((p) => p.id === activeId) ?? null;
          const link = children.find((c: any) => {
            return profiles.some((p) => p.id === activeId && p.user_id === c.child);
          }) as any;
          childName = link?.child_detail?.full_name ?? null;
          if (!childName && primary) childName = primary.display_name;
        }
        if (!primary) primary = pickBestProfile(profiles);
        setHasProfile(profiles.length > 0);
      } else {
        const profiles = await listProfiles().catch(() => [] as PlayerProfile[]);
        primary = pickBestProfile(profiles);
        setHasProfile(profiles.length > 0);
      }

      setProfile(primary);
      setActiveChildName(childName);

      setModalityMissing(false);
      if (primary) {
        syncModalityFromProfile(primary);
        // Prefer preferred_modality from the API response; fall back to localStorage cache.
        // This ensures the modality filter is always up-to-date even after profile changes
        // on another device, and correctly filters compatible tournaments per dependent profile.
        const modality = primary.preferred_modality || getProfileModality(primary.id);
        const compatData = await compatibleForProfile(primary.id, {
          page_size: 20,
          ...(modality ? { modality } : {}),
        }).catch((err: any) => {
          if (err?.response?.data?.code === 'modality_required') {
            setModalityMissing(true);
          }
          return { results: [] as TournamentEditionList[] };
        });
        const filtered = (compatData.results || [])
          .filter((t) => ACTIVE_STATUSES.has(t.status ?? ''))
          .slice(0, 8);
        setCompat(filtered);
      } else {
        setCompat([]);
      }
    } finally {
      setLoading(false);
      hasLoadedRef.current = true;
    }
  }, [user?.id, user?.role]);

  // Initial load + reload when user changes
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reload when returning to this tab (browser visibility change)
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        const wasEdited = consumeProfileDirty();
        if (wasEdited || hasLoadedRef.current) loadData();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [loadData]);

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <Loader2 className="w-8 h-8 text-accent-neon animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Greeting ── */}
      <section>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted">Olá,</div>
            <h1 className="text-2xl font-bold">
              {user?.full_name || profile?.display_name || user?.email?.split('@')[0] || 'Jogador'}
            </h1>
            {profile && (
              <div className="text-xs text-text-secondary mt-1 flex items-center gap-1 flex-wrap">
                {activeChildName && (
                  <span className="flex items-center gap-1 text-accent-blue font-semibold">
                    <User className="w-3 h-3" />{activeChildName}
                  </span>
                )}
                {profile.tennis_class && <span>Classe {profile.tennis_class}</span>}
                {profile.sporting_age ? <span>• {profile.sporting_age} anos</span> : null}
                {profile.home_state && <span>• {profile.home_state}</span>}
              </div>
            )}
          </div>
          <Link to="/alertas" className="btn-ghost relative">
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-accent-neon text-bg-base text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </Link>
        </div>
      </section>

      {/* ── Complete profile CTA (only shown if no profile) ── */}
      {!hasProfile && (
        <div className="card flex items-start gap-3 border border-accent-neon/30 bg-accent-neon/5">
          <Sparkles className="w-5 h-5 text-accent-neon shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Complete seu perfil</p>
            <p className="text-xs text-text-muted mt-0.5">
              Informe sua categoria, idade e localização para ver torneios compatíveis com você.
            </p>
          </div>
          <Link to="/onboarding" className="btn-primary !py-1.5 !px-3 text-xs shrink-0">
            Configurar
          </Link>
        </div>
      )}

      {/* ── Compatible tournaments (only when profile exists) ── */}
      {profile && modalityMissing && (
        <div className="card flex items-start gap-3 border border-amber-500/30 bg-amber-500/5">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-amber-400">Modalidade não configurada</p>
            <p className="text-xs text-text-secondary mt-0.5">
              Configure a modalidade esportiva no perfil para ver torneios compatíveis (Tênis, Beach Tennis, etc.).
            </p>
          </div>
          <Link to="/perfil" className="btn-secondary !py-1.5 !px-3 text-xs shrink-0">
            Perfil
          </Link>
        </div>
      )}
      {profile && !modalityMissing && (
        <Section
          title={activeChildName ? `Compatíveis — ${activeChildName}` : 'Compatíveis com você'}
          subtitle="Baseado no perfil ativo: categoria, modalidade e localização"
          icon={<Sparkles className="w-4 h-4 text-accent-neon" />}
          emptyText="Nenhum torneio compatível encontrado. Verifique se o perfil está completo (modalidade, classe, UF) ou aguarde novas ingestões (a cada hora)."
          items={compat}
          viewAll="/torneios"
          accent
        />
      )}

      {/* ── Closing soon ── */}
      <Section
        title="Inscrições fechando"
        subtitle="Próximos 14 dias"
        icon={<Clock className="w-4 h-4 text-status-closing" />}
        emptyText="Nenhum prazo se aproximando."
        items={closing}
      />

      {/* ── Recently added ── */}
      <Section
        title="Recentemente adicionados"
        subtitle="Últimos torneios agregados pelas fontes"
        icon={<CalendarDays className="w-4 h-4 text-text-muted" />}
        items={recent}
        viewAll="/torneios"
        emptyText="Nenhum torneio na base ainda. As ingestões acontecem automaticamente a cada hora."
      />
    </div>
  );
};

const Section: React.FC<{
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  items: TournamentEditionList[];
  emptyText: string;
  viewAll?: string;
  accent?: boolean;
}> = ({ title, subtitle, icon, items, emptyText, viewAll, accent = false }) => (
  <section>
    <div className="flex items-end justify-between mb-3">
      <div>
        <h2 className="font-semibold flex items-center gap-1.5">
          {icon}
          <span className={accent ? 'text-accent-neon' : ''}>{title}</span>
        </h2>
        {subtitle && <p className="text-xs text-text-muted">{subtitle}</p>}
      </div>
      {viewAll && (
        <Link to={viewAll} className="text-xs text-accent-blue hover:underline flex items-center gap-0.5">
          Ver todos <ChevronRight className="w-3 h-3" />
        </Link>
      )}
    </div>
    {items.length === 0 ? (
      <div className="card text-center text-sm text-text-muted py-8">{emptyText}</div>
    ) : (
      <div className="space-y-3">
        {items.map((ed) => (
          <TournamentCard key={ed.id} edition={ed} showEligibility={accent} />
        ))}
      </div>
    )}
  </section>
);
