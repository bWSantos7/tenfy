import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Clock, Sparkles, Bell, Loader2, CalendarDays } from 'lucide-react';
import { TournamentEditionList, PlayerProfile } from '../types';
import { closingSoon, compatibleForProfile, listEditions } from '../services/tournaments';
import { listProfiles, unreadAlerts } from '../services/data';
import { TournamentCard } from '../components/TournamentCard';
import { useAuth } from '../contexts/AuthContext';
import { pickBestProfile } from '../utils/profile';

export const HomePage: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [compat, setCompat] = useState<TournamentEditionList[]>([]);
  const [closing, setClosing] = useState<TournamentEditionList[]>([]);
  const [recent, setRecent] = useState<TournamentEditionList[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const [profiles, closingData, recentData, alerts] = await Promise.all([
          listProfiles().catch(() => []),
          closingSoon(14).catch(() => []),
          listEditions({ page_size: 8, ordering: '-created_at' }).catch(() => ({ results: [] } as any)),
          unreadAlerts().catch(() => []),
        ]);
        const primary = pickBestProfile(profiles);
        setHasProfile(profiles.length > 0);
        setProfile(primary);
        setClosing((closingData as TournamentEditionList[]).slice(0, 6));
        setRecent((recentData.results || []).slice(0, 6));
        setUnreadCount((alerts || []).length);

        if (primary) {
          const compatData = await compatibleForProfile(primary.id, { page_size: 8 }).catch(
            () => ({ results: [] as TournamentEditionList[] }),
          );
          setCompat((compatData.results || []).slice(0, 8));
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
              <div className="text-xs text-text-secondary mt-1">
                {profile.tennis_class && `Classe ${profile.tennis_class}`}
                {profile.sporting_age ? ` • ${profile.sporting_age} anos esportivos` : ''}
                {profile.home_state && ` • ${profile.home_state}`}
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
      {profile && (
        <Section
          title="Compatíveis com você"
          subtitle="Baseado no seu perfil, categoria e localização"
          icon={<Sparkles className="w-4 h-4 text-accent-neon" />}
          emptyText="Nenhum torneio compatível encontrado ainda. Verifique se seu perfil está completo ou aguarde novas ingestões (a cada hora)."
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
