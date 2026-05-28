import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Clock, Sparkles, Bell, Loader2, CalendarDays, User, AlertTriangle } from 'lucide-react';
import { TournamentEditionList, PlayerProfile } from '../types';
import { closingSoon, compatibleForProfile, listEditions } from '../services/tournaments';
import { listChildren, listProfiles, unreadAlerts } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { useAuth } from '../contexts/AuthContext';
import { pickBestProfile } from '../utils/profile';
import { getActiveProfileId, setActiveProfileId as persistActiveProfileId } from '../utils/activeProfile';
import { consumeProfileDirty } from '../utils/profileRefresh';
import { getProfileModality, syncModalityFromProfile } from '../utils/profileModality';

const ACTIVE_STATUSES = new Set(['open', 'closing_soon', 'announced', 'in_progress']);

interface ProfileOption {
  profile: PlayerProfile;
  childName: string;
}

export const HomePage: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [compatLoading, setCompatLoading] = useState(false);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [activeChildName, setActiveChildName] = useState<string | null>(null);
  const [profileOptions, setProfileOptions] = useState<ProfileOption[]>([]);
  const [hasProfile, setHasProfile] = useState(false);
  const [compat, setCompat] = useState<TournamentEditionList[]>([]);
  const [closing, setClosing] = useState<TournamentEditionList[]>([]);
  const [recent, setRecent] = useState<TournamentEditionList[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [modalityMissing, setModalityMissing] = useState(false);
  const hasLoadedRef = useRef(false);

  const loadCompat = useCallback(async (p: PlayerProfile) => {
    setCompatLoading(true);
    setModalityMissing(false);
    try {
      syncModalityFromProfile(p);
      const modality = p.preferred_modality || getProfileModality(p.id);
      const compatData = await compatibleForProfile(p.id, {
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
    } finally {
      setCompatLoading(false);
    }
  }, []);

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

      let primary: PlayerProfile | null = null;
      let childName: string | null = null;
      let options: ProfileOption[] = [];

      if (user?.role === 'parent' && user.id) {
        const [profiles, children] = await Promise.all([
          listProfiles().catch(() => [] as PlayerProfile[]),
          listChildren().catch(() => []),
        ]);

        options = profiles.map((p) => {
          const link = children.find((c) => c.child === p.user_id) as any;
          const name = link?.child_detail?.full_name || p.display_name;
          return { profile: p, childName: name };
        });

        setProfileOptions(options);
        setHasProfile(profiles.length > 0);

        const activeId = getActiveProfileId(user.id);
        const activeOption = activeId ? options.find((o) => o.profile.id === activeId) : null;
        primary = activeOption?.profile ?? null;
        childName = activeOption?.childName ?? null;
      } else {
        const profiles = await listProfiles().catch(() => [] as PlayerProfile[]);
        primary = pickBestProfile(profiles);
        setHasProfile(profiles.length > 0);
      }

      setProfile(primary);
      setActiveChildName(childName);

      if (primary) {
        await loadCompat(primary);
      } else {
        setCompat([]);
        setModalityMissing(false);
      }
    } finally {
      setLoading(false);
      hasLoadedRef.current = true;
    }
  }, [user?.id, user?.role, loadCompat]);

  async function switchProfile(opt: ProfileOption) {
    if (opt.profile.id === profile?.id) return;
    setProfile(opt.profile);
    setActiveChildName(opt.childName);
    if (user?.id) persistActiveProfileId(user.id, opt.profile.id);
    // Clear saved tournament filters so TournamentsPage re-applies the new
    // profile's modality as the default filter on the next visit.
    try { sessionStorage.removeItem('tenfy_tournament_filters'); } catch {}
    await loadCompat(opt.profile);
  }

  useEffect(() => {
    loadData();
  }, [loadData]);

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

        {/* ── Seletor de dependente (pai com múltiplos perfis) ── */}
        {user?.role === 'parent' && profileOptions.length > 1 && (
          <div className="flex gap-2 mt-3 overflow-x-auto pb-1 scrollbar-none">
            {profileOptions.map((opt) => {
              const isActive = opt.profile.id === profile?.id;
              const modalityTag =
                opt.profile.preferred_modality === 'beach_tennis' ? 'BT'
                : opt.profile.preferred_modality === 'tennis' ? 'TN'
                : opt.profile.preferred_modality === 'padel' ? 'PD'
                : null;
              return (
                <button
                  key={opt.profile.id}
                  onClick={() => switchProfile(opt)}
                  className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-colors ${
                    isActive
                      ? 'bg-accent-neon text-bg-base border-accent-neon'
                      : 'bg-bg-card border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent-neon/50'
                  }`}
                >
                  <User className="w-3 h-3 shrink-0" />
                  <span className="truncate max-w-[120px]">{opt.childName}</span>
                  {modalityTag && (
                    <span className={`text-[10px] font-bold px-1 rounded ${isActive ? 'bg-bg-base/20' : 'bg-bg-elevated'}`}>
                      {modalityTag}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
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

      {/* ── Modality missing banner ── */}
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

      {/* ── No profile selected (parent with multiple profiles, no explicit selection yet) ── */}
      {!profile && user?.role === 'parent' && profileOptions.length > 1 && (
        <div className="card flex items-start gap-3 border border-accent-neon/30 bg-accent-neon/5">
          <User className="w-5 h-5 text-accent-neon shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Selecione um dependente</p>
            <p className="text-xs text-text-muted mt-0.5">
              Escolha o perfil acima para ver os torneios compatíveis com esse atleta.
            </p>
          </div>
        </div>
      )}

      {/* ── Compatible tournaments ── */}
      {profile && !modalityMissing && (
        <Section
          title={activeChildName ? `Compatíveis — ${activeChildName}` : 'Compatíveis com você'}
          subtitle="Baseado no perfil ativo: categoria, modalidade e localização"
          icon={<Sparkles className="w-4 h-4 text-accent-neon" />}
          emptyText="Nenhum torneio compatível encontrado. Verifique se o perfil está completo (modalidade, classe, UF) ou aguarde novas ingestões (a cada hora)."
          items={compat}
          viewAll="/torneios"
          accent
          loading={compatLoading}
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
  loading?: boolean;
}> = ({ title, subtitle, icon, items, emptyText, viewAll, accent = false, loading = false }) => (
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
    {loading ? (
      <div className="py-8 flex justify-center">
        <Loader2 className="w-6 h-6 text-accent-neon animate-spin" />
      </div>
    ) : items.length === 0 ? (
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
