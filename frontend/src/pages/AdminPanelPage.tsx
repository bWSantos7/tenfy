import React, { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Database, Loader2, Link2,
  Play, RefreshCcw, Search, Shield, ShieldOff,
  Trash2, UserCog, X, BarChart2,
  KeyRound, Unlock, CreditCard, Users, Eye, Trophy,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts';
import api, { extractApiError } from '../services/api';
import { TournamentEditionList } from '../types';
import { TournamentCard } from '../components/TournamentCard';
import { ErrorBoundary } from '../components/ErrorBoundary';

// ─── Types ───────────────────────────────────────────────────────────────────

interface Dashboard {
  counts: {
    tournaments_total: number;
    tournaments_open: number;
    tournaments_closing_soon: number;
    data_sources_enabled: number;
    data_sources_total: number;
    manual_overrides: number;
    low_confidence: number;
    missing_official_url: number;
  };
  ingestion: { runs_24h: number; failed_24h: number; partial_24h: number };
  alerts: { total_7d: number; failed_7d: number };
  audit: { actions_24h: number };
}

interface ReviewQueue {
  low_confidence: TournamentEditionList[];
  missing_official_url: TournamentEditionList[];
  recently_changed: TournamentEditionList[];
}

interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  role: string;
  profile_type?: string;
  profile_label?: string;
  plan?: string | null;
  plan_slug?: string | null;
  plan_status?: string;
  plan_is_blocked?: boolean;
  billing_period?: string | null;
  is_login_locked?: boolean;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  email_verified: boolean;
  marketing_consent: boolean;
  created_at: string;
  last_login: string | null;
}

interface LinkUser { link_id: number; id: number; full_name: string; email: string; role: string }

interface AdminUserDetail extends AdminUser {
  consent_version?: string;
  last_login_ip?: string | null;
  failed_login_attempts?: number;
  login_locked_until?: string | null;
  lock_seconds_remaining?: number;
  sport_profile?: {
    display_name: string; modality: string; competitive_level: string;
    competitive_level_label: string; birth_year: number | null; birth_date: string | null;
    age: number | null; gender: string; gender_label: string;
    federation: { id: number; name: string; uf: string } | null;
    home_state: string; home_city: string; travel_states: string[];
    dominant_hand: string; ti_player_id: string | null;
    utr_singles: string; utr_doubles: string; utr_profile_url: string;
    ti_rankings: unknown[]; external_rankings: Record<string, unknown>[]; profiles_count: number;
  } | null;
  tournaments?: {
    registered: { id: number; edition: string; payment_status: string; is_withdrawn: boolean; registered_at: string }[];
    watching: { id: number; edition: string; user_status: string }[];
    results: { id: number; category_played: string; position: number | null; wins: number; losses: number }[];
  };
  links?: { responsibles: LinkUser[]; dependents: LinkUser[] };
}

const PLAN_STATUS_LABELS: Record<string, string> = {
  active: 'Ativo', trial: 'Tester/Trial', pending: 'Pendente',
  canceled: 'Cancelado', expired: 'Expirado', unpaid: 'Inadimplente', none: 'Sem plano',
};

interface AdminStats {
  registrations: { date: string; registrations: number }[];
  users_by_role: { role: string; count: number }[];
  tournaments_by_status: { status: string; count: number }[];
  watchlist_by_status: { status: string; count: number }[];
  totals: { users: number; active_users: number; new_users_period: number };
}

type Tab = 'dashboard' | 'stats' | 'users' | 'leads' | 'sources' | 'connectors' | 'editions';

const EDITION_STATUS_LABELS: Record<string, string> = {
  unknown:   'Não informado',
  announced: 'Anunciado',
  open:      'Aberto',
  upcoming:  'Em breve',
  closed:    'Encerrado',
  closing_soon: 'Encerrando em breve',
  draws_published: 'Chaves publicadas',
  in_progress: 'Em andamento',
  finished:  'Finalizado',
  canceled:  'Cancelado',
  completed: 'Concluído',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'Alta qualidade dos dados',
  med:  'Qualidade média dos dados',
  medium: 'Qualidade média dos dados',
  low:  'Baixa qualidade dos dados',
};

const RUN_STATUS_LABELS: Record<string, string> = {
  success: 'Concluído',
  partial: 'Parcial',
  failed:  'Falhou',
  running: 'Em execução',
};

const UNKNOWN_STATUS_LABEL = 'Status não informado';

// ─── Main page ────────────────────────────────────────────────────────────────

export const AdminPanelPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('dashboard');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Painel administrativo</h1>
        <p className="text-sm text-text-muted">Curadoria, ingestão, usuários e monitoramento</p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {([
          ['dashboard',  'Dashboard'],
          ['stats',      'Estatísticas'],
          ['users',      'Usuários'],
          ['leads',      'Leads'],
          ['sources',    'Fontes'],
          ['connectors', 'Conectores'],
          ['editions',   'Torneios'],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
              tab === key
                ? 'border-accent-neon text-accent-neon'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'dashboard'  && <ErrorBoundary><DashboardTab /></ErrorBoundary>}
      {tab === 'stats'      && <ErrorBoundary><StatsTab /></ErrorBoundary>}
      {tab === 'users'      && <ErrorBoundary><UsersTab /></ErrorBoundary>}
      {tab === 'leads'      && <ErrorBoundary><WaitlistLeadsTab /></ErrorBoundary>}
      {tab === 'sources'    && <ErrorBoundary><SourcesTab /></ErrorBoundary>}
      {tab === 'connectors' && <ErrorBoundary><ConnectorsTab /></ErrorBoundary>}
      {tab === 'editions'   && <ErrorBoundary><EditionsAdminTab /></ErrorBoundary>}
    </div>
  );
};

// ─── Dashboard tab ────────────────────────────────────────────────────────────

const DashboardTab: React.FC = () => {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [d, q] = await Promise.all([
        api.get<Dashboard>('/api/admin-panel/dashboard/'),
        api.get<ReviewQueue>('/api/admin-panel/review-queue/'),
      ]);
      setDash(d.data);
      setQueue(q.data);
    } catch (err) {
      const message = extractApiError(err);
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function runAll() {
    setRunning(true);
    try {
      await api.post('/api/ingestion/runs/run-all/');
      toast.success('Ingestão disparada em background');
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return <div className="py-16 flex justify-center"><Loader2 className="w-8 h-8 text-accent-neon animate-spin" /></div>;
  }

  if (!dash) {
    return (
      <div className="card text-center py-8 text-sm text-text-muted">
        {error || 'Não foi possível carregar o dashboard.'}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2">
        <button className="btn-secondary !py-2 !px-3" onClick={load} title="Atualizar">
          <RefreshCcw className="w-4 h-4" />
        </button>
        <button className="btn-primary !py-2 !px-3 flex items-center gap-1" onClick={runAll} disabled={running}>
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Ingerir agora
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Torneios" value={dash.counts.tournaments_total} icon={<Database />} />
        <StatCard label="Abertos" value={dash.counts.tournaments_open} accent />
        <StatCard label="Fechando" value={dash.counts.tournaments_closing_soon} warn />
        <StatCard label="Fontes ativas" value={`${dash.counts.data_sources_enabled}/${dash.counts.data_sources_total}`} />
        <StatCard label="Overrides manuais" value={dash.counts.manual_overrides} />
        <StatCard label="Dados para revisar" value={dash.counts.low_confidence} warn />
        <StatCard label="Sem link oficial" value={dash.counts.missing_official_url} warn />
        <StatCard label="Execuções 24h" value={`${dash.ingestion.runs_24h} (${dash.ingestion.failed_24h} falhas)`} />
      </div>

      {queue && (
        <>
          <QueueSection title="Dados para revisar" icon={<AlertTriangle className="w-4 h-4 text-status-closing" />} items={queue.low_confidence} emptyText="Nenhuma edição com qualidade de dados baixa." />
          <QueueSection title="Sem link oficial" icon={<Link2 className="w-4 h-4 text-status-canceled" />} items={queue.missing_official_url} emptyText="Todas as edições possuem link oficial." />
          <QueueSection title="Alteradas recentemente" icon={<RefreshCcw className="w-4 h-4 text-accent-blue" />} items={queue.recently_changed} emptyText="Nenhuma alteração recente." />
        </>
      )}
    </div>
  );
};

// ─── Stats tab ────────────────────────────────────────────────────────────────

// Chart colors — must use hex values; Recharts does not resolve CSS custom properties.
// Values are kept in sync with tailwind.config.js design tokens.
const CHART_COLORS = [
  '#3DC55E', // accent.neon   → status-open (Tenfy green)
  '#3B82F6', // accent.blue
  '#F07B30', // status.closing (Tenfy orange)
  '#EF4444', // status.canceled
  '#8B5CF6', // status.progress
];

const StatsTab: React.FC = () => {
  const [data, setData] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  async function load(d = days) {
    setLoading(true);
    try {
      const res = await api.get<AdminStats>(`/api/admin-panel/stats/?days=${d}`);
      setData(res.data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading || !data) {
    return <div className="py-16 flex justify-center"><Loader2 className="w-8 h-8 text-accent-neon animate-spin" /></div>;
  }

  const tooltipStyle = {
    backgroundColor: 'rgb(var(--bg-card))',
    border: '1px solid rgb(var(--border-subtle))',
    borderRadius: '8px',
    color: 'rgb(var(--text-primary))',
    fontSize: '12px',
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart2 size={18} className="text-accent-neon" />
          <span className="font-semibold">Estatísticas da plataforma</span>
        </div>
        <div className="flex items-center gap-2">
          {[7, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => { setDays(d); load(d); }}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                days === d
                  ? 'border-accent-neon text-accent-neon bg-accent-neon/10'
                  : 'border-border-subtle text-text-muted hover:text-text-primary'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card !p-3 text-center">
          <div className="text-[10px] text-text-muted uppercase mb-1">Total usuários</div>
          <div className="text-2xl font-bold text-accent-neon">{data.totals.users}</div>
        </div>
        <div className="card !p-3 text-center">
          <div className="text-[10px] text-text-muted uppercase mb-1">Ativos</div>
          <div className="text-2xl font-bold">{data.totals.active_users}</div>
        </div>
        <div className="card !p-3 text-center">
          <div className="text-[10px] text-text-muted uppercase mb-1">Novos ({days}d)</div>
          <div className="text-2xl font-bold text-accent-blue">{data.totals.new_users_period}</div>
        </div>
      </div>

      {/* Registration trend */}
      <div className="card !p-4 space-y-3">
        <h3 className="text-sm font-semibold text-text-secondary">Novos cadastros por dia</h3>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data.registrations} margin={{ top: 4, right: 4, bottom: 4, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }}
              tickFormatter={v => v.slice(5)}
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} labelFormatter={v => String(v)} />
            <Line
              type="monotone"
              dataKey="registrations"
              name="Cadastros"
              stroke="#3DC55E"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Side-by-side bar charts */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="card !p-4 space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary">Usuários por perfil</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={data.users_by_role} margin={{ top: 4, right: 4, bottom: 4, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="role" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} tickFormatter={(v: string) => ROLE_LABELS[v] ?? 'Perfil não informado'} />
              <YAxis tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Usuários" radius={[4, 4, 0, 0]}>
                {data.users_by_role.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card !p-4 space-y-3">
          <h3 className="text-sm font-semibold text-text-secondary">Torneios por status</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={data.tournaments_by_status} margin={{ top: 4, right: 4, bottom: 4, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="status" tick={{ fontSize: 9, fill: 'rgb(var(--text-muted))' }} tickFormatter={(v: string) => EDITION_STATUS_LABELS[v] ?? UNKNOWN_STATUS_LABEL} />
              <YAxis tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Torneios" fill="#00B2FF" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card !p-4 space-y-3 md:col-span-2">
          <h3 className="text-sm font-semibold text-text-secondary">Watchlist por status</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.watchlist_by_status} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
              <YAxis type="category" dataKey="status" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} width={80} tickFormatter={(v: string) => EDITION_STATUS_LABELS[v] ?? UNKNOWN_STATUS_LABEL} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Itens" fill="#FFB020" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

// ─── Users tab ────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  player: 'Jogador',
  coach: 'Treinador',
  parent: 'Pai/Responsável',
  admin: 'Administrador',
};

const PlanBadge: React.FC<{ user: AdminUser }> = ({ user }) => {
  const status = user.plan_status || 'none';
  const color = status === 'active' ? 'green'
    : status === 'trial' ? 'neon'
    : status === 'pending' ? 'amber'
    : status === 'none' ? 'gray' : 'red';
  const planName = user.plan || 'Sem plano';
  return <Badge color={color}>{planName} · {PLAN_STATUS_LABELS[status] ?? status}</Badge>;
};

const UsersTab: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [viewing, setViewing] = useState<AdminUser | null>(null);
  const [deleting, setDeleting] = useState<AdminUser | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function load(q = '') {
    setLoading(true);
    try {
      const res = await api.get<AdminUser[]>('/api/admin-panel/users/', { params: q ? { q } : {} });
      setUsers(res.data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function onSearch(val: string) {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(val), 400);
  }

  async function handleDelete(user: AdminUser) {
    try {
      await api.delete(`/api/admin-panel/users/${user.id}/`);
      toast.success(`${user.email} removido.`);
      setDeleting(null);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  function onSaved(updated: AdminUser) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)));
    setEditing(null);
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          className="input-base pl-9"
          placeholder="Buscar por e-mail ou nome…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
      ) : users.length === 0 ? (
        <div className="card text-center py-8 text-text-muted text-sm">Nenhum usuário encontrado.</div>
      ) : (
        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.id} className="card !p-3 flex items-center gap-3">
              <button
                onClick={() => setViewing(u)}
                className="w-9 h-9 rounded-full bg-bg-surface flex items-center justify-center shrink-0 text-sm font-bold text-accent-neon uppercase"
                title="Ver detalhes"
              >
                {(u.full_name || u.email)[0]}
              </button>
              <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setViewing(u)}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm truncate">{u.full_name || '—'}</span>
                  <Badge color="gray">#{u.id}</Badge>
                  {u.profile_label && <Badge color="blue">{u.profile_label}</Badge>}
                  {!u.is_active && <Badge color="red">Inativo</Badge>}
                  {u.is_login_locked && <Badge color="red">Login bloqueado</Badge>}
                </div>
                <div className="text-xs text-text-muted truncate">{u.email}</div>
                <div className="mt-1"><PlanBadge user={u} /></div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => setViewing(u)}
                  className="p-1.5 rounded hover:bg-bg-surface text-text-muted hover:text-text-primary transition-colors"
                  title="Ver detalhes"
                >
                  <Eye className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setEditing(u)}
                  className="p-1.5 rounded hover:bg-bg-surface text-text-muted hover:text-text-primary transition-colors"
                  title="Editar"
                >
                  <UserCog className="w-4 h-4" />
                </button>
                {!u.is_superuser && (
                  <button
                    onClick={() => setDeleting(u)}
                    className="p-1.5 rounded hover:bg-bg-surface text-text-muted hover:text-red-400 transition-colors"
                    title="Deletar"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {viewing && (
        <UserDetailModal
          userId={viewing.id}
          onClose={() => setViewing(null)}
          onChanged={() => load(search)}
          onEdit={() => { setEditing(viewing); setViewing(null); }}
        />
      )}
      {editing && <EditUserModal user={editing} onClose={() => setEditing(null)} onSaved={onSaved} />}
      {deleting && (
        <ConfirmModal
          title="Deletar usuário"
          message={`Tem certeza que deseja deletar ${deleting.email}? Esta ação é irreversível.`}
          onConfirm={() => handleDelete(deleting)}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
};

// ─── Edit modal ───────────────────────────────────────────────────────────────

const EditUserModal: React.FC<{
  user: AdminUser;
  onClose: () => void;
  onSaved: (u: AdminUser) => void;
}> = ({ user, onClose, onSaved }) => {
  const [form, setForm] = useState({
    full_name: user.full_name,
    email: user.email,
    role: user.role,
    is_active: user.is_active,
    is_staff: user.is_staff,
  });
  const [saving, setSaving] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.patch<AdminUser>(`/api/admin-panel/users/${user.id}/`, form);
      toast.success('Usuário atualizado.');
      onSaved(res.data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="bg-bg-card border border-border rounded-2xl w-full max-w-sm p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-lg">Editar usuário</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        </div>
        <p className="text-xs text-text-muted">#{user.id}</p>
        <form onSubmit={save} className="space-y-3">
          <div>
            <label className="text-xs text-text-secondary mb-1 block">Nome</label>
            <input
              className="input-base"
              value={form.full_name}
              onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs text-text-secondary mb-1 block">E-mail</label>
            <input
              type="email"
              className="input-base"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-xs text-text-secondary mb-1 block">Perfil</label>
            <select
              className="input-base"
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
            >
              <option value="player">Jogador</option>
              <option value="coach">Treinador</option>
              <option value="parent">Pai/Responsável</option>
              <option value="admin">Administrador</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="accent-accent-neon"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Conta ativa
          </label>
          {!user.is_superuser && (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                className="accent-accent-neon"
                checked={form.is_staff}
                onChange={(e) => setForm((f) => ({ ...f, is_staff: e.target.checked }))}
              />
              <span className="flex items-center gap-1">
                {form.is_staff
                  ? <Shield className="w-3.5 h-3.5 text-accent-neon" />
                  : <ShieldOff className="w-3.5 h-3.5 text-text-muted" />}
                Acesso de staff (admin panel)
              </span>
            </label>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-secondary flex-1">Cancelar</button>
            <button type="submit" disabled={saving} className="btn-primary flex-1 flex items-center justify-center gap-2">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Salvar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─── User detail modal (audit / ações) ──────────────────────────────────────────

const DetailRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex justify-between gap-3 text-sm py-1 border-b border-border/40 last:border-0">
    <span className="text-text-muted">{label}</span>
    <span className="text-right font-medium break-words">{value ?? '—'}</span>
  </div>
);

const DetailSection: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode }> = ({ title, icon, children }) => (
  <section className="card !p-3">
    <h3 className="text-sm font-semibold flex items-center gap-2 mb-2">{icon} {title}</h3>
    {children}
  </section>
);

const UserDetailModal: React.FC<{
  userId: number;
  onClose: () => void;
  onChanged: () => void;
  onEdit: () => void;
}> = ({ userId, onClose, onChanged, onEdit }) => {
  const [data, setData] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [planSlug, setPlanSlug] = useState('');
  const [planStatus, setPlanStatus] = useState('');

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<AdminUserDetail>(`/api/admin-panel/users/${userId}/`);
      setData(res.data);
      setPlanSlug(res.data.plan_slug || '');
      setPlanStatus(res.data.plan_status && res.data.plan_status !== 'none' ? res.data.plan_status : '');
    } catch (err) {
      toast.error(extractApiError(err));
      onClose();
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [userId]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      await load();
      onChanged();
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }

  function resetPassword() {
    const pwd = window.prompt('Nova senha (mínimo 6 caracteres):');
    if (!pwd) return;
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/set-password/`, { password: pwd });
      toast.success('Senha redefinida.');
    });
  }

  function unlockLogin() {
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/unlock-login/`, {});
      toast.success('Login desbloqueado.');
    });
  }

  function savePlan() {
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/plan/`, {
        plan_slug: planSlug || undefined,
        status: planStatus || undefined,
      });
      toast.success('Plano atualizado.');
    });
  }

  function makeTester() {
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/plan/`, { plan_slug: 'tester', status: 'active' });
      toast.success('Plano Tester liberado.');
    });
  }

  function removeLink(role: 'parent' | 'child', counterpartId: number) {
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/links/`, { action: 'remove', role, counterpart_id: counterpartId });
      toast.success('Vínculo removido.');
    });
  }

  function addLink(role: 'parent' | 'child') {
    const id = window.prompt(role === 'parent' ? 'ID do responsável a vincular:' : 'ID do dependente a vincular:');
    if (!id) return;
    act(async () => {
      await api.post(`/api/admin-panel/users/${userId}/links/`, { action: 'add', role, counterpart_id: Number(id) });
      toast.success('Vínculo criado.');
    });
  }

  const sp = data?.sport_profile;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-3 py-6 overflow-y-auto">
      <div className="bg-bg-card border border-border rounded-2xl w-full max-w-lg p-5 space-y-3 my-auto">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-lg flex items-center gap-2"><UserCog className="w-5 h-5 text-accent-neon" /> Detalhes do usuário</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-5 h-5" /></button>
        </div>

        {loading || !data ? (
          <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
        ) : (
          <>
            {/* Conta */}
            <DetailSection title="Conta" icon={<UserCog className="w-4 h-4 text-accent-neon" />}>
              <DetailRow label="ID" value={`#${data.id}`} />
              <DetailRow label="Nome" value={data.full_name || '—'} />
              <DetailRow label="E-mail" value={data.email} />
              <DetailRow label="Telefone" value={data.phone || '—'} />
              <DetailRow label="Perfil" value={data.profile_label} />
              <DetailRow label="Conta" value={data.is_active ? 'Ativa' : 'Inativa'} />
              <DetailRow label="E-mail verificado" value={data.email_verified ? 'Sim' : 'Não'} />
              <DetailRow label="Login bloqueado" value={data.is_login_locked
                ? `Sim (${Math.ceil((data.lock_seconds_remaining || 0) / 60)} min restantes)` : 'Não'} />
              <DetailRow label="Tentativas falhas" value={data.failed_login_attempts ?? 0} />
              <DetailRow label="Criado em" value={fmtDate(data.created_at)} />
              <DetailRow label="Último login" value={data.last_login ? fmtDate(data.last_login) : 'Nunca'} />
            </DetailSection>

            {/* Plano */}
            <DetailSection title="Plano" icon={<CreditCard className="w-4 h-4 text-accent-neon" />}>
              <DetailRow label="Plano" value={data.plan || 'Sem plano'} />
              <DetailRow label="Status" value={<PlanBadge user={data} />} />
              <div className="grid grid-cols-2 gap-2 mt-2">
                <select className="input-base !py-1.5 text-sm" value={planSlug} onChange={(e) => setPlanSlug(e.target.value)}>
                  <option value="">(manter plano)</option>
                  <option value="individual">Individual</option>
                  <option value="familia">Família</option>
                  <option value="tester">Tester</option>
                </select>
                <select className="input-base !py-1.5 text-sm" value={planStatus} onChange={(e) => setPlanStatus(e.target.value)}>
                  <option value="">(manter status)</option>
                  <option value="active">Ativo</option>
                  <option value="pending">Pendente</option>
                  <option value="trial">Trial</option>
                  <option value="canceled">Cancelado</option>
                  <option value="expired">Expirado</option>
                  <option value="unpaid">Inadimplente</option>
                </select>
              </div>
              <div className="flex gap-2 mt-2">
                <button disabled={busy} onClick={savePlan} className="btn-secondary flex-1 text-sm">Aplicar plano</button>
                <button disabled={busy} onClick={makeTester} className="btn-secondary flex-1 text-sm">Liberar Tester</button>
              </div>
            </DetailSection>

            {/* Perfil esportivo */}
            <DetailSection title="Perfil esportivo" icon={<Trophy className="w-4 h-4 text-accent-neon" />}>
              {!sp ? (
                <p className="text-sm text-text-muted">Sem perfil esportivo cadastrado.</p>
              ) : (
                <>
                  <DetailRow label="Modalidade" value={sp.modality || '—'} />
                  <DetailRow label="Categoria/Nível" value={sp.competitive_level_label || sp.competitive_level} />
                  <DetailRow label="Nascimento" value={sp.birth_date || sp.birth_year || '—'} />
                  <DetailRow label="Idade" value={sp.age ?? '—'} />
                  <DetailRow label="Gênero" value={sp.gender_label || '—'} />
                  <DetailRow label="Federação" value={sp.federation ? `${sp.federation.name} (${sp.federation.uf})` : '—'} />
                  <DetailRow label="Estado" value={sp.home_state || '—'} />
                  <DetailRow label="Cidade" value={sp.home_city || '—'} />
                  <DetailRow label="UFs de interesse" value={(sp.travel_states || []).join(', ') || '—'} />
                  <DetailRow label="UTR (simples/duplas)" value={`${sp.utr_singles || '—'} / ${sp.utr_doubles || '—'}`} />
                  <DetailRow label="ID Tênis Integrado" value={sp.ti_player_id || '—'} />
                  <DetailRow label="Rankings externos" value={sp.external_rankings?.length ?? 0} />
                </>
              )}
            </DetailSection>

            {/* Torneios */}
            <DetailSection title="Torneios" icon={<Trophy className="w-4 h-4 text-accent-neon" />}>
              <DetailRow label="Inscritos" value={data.tournaments?.registered.length ?? 0} />
              <DetailRow label="Acompanhados" value={data.tournaments?.watching.length ?? 0} />
              <DetailRow label="Resultados" value={data.tournaments?.results.length ?? 0} />
            </DetailSection>

            {/* Vínculos */}
            <DetailSection title="Vínculos" icon={<Users className="w-4 h-4 text-accent-neon" />}>
              <div className="text-xs text-text-muted mb-1">Responsáveis</div>
              {data.links?.responsibles.length ? data.links.responsibles.map((r) => (
                <div key={r.link_id} className="flex items-center justify-between text-sm py-1">
                  <span className="truncate">{r.full_name || r.email} <span className="text-text-muted">#{r.id}</span></span>
                  <button disabled={busy} onClick={() => removeLink('parent', r.id)} className="text-red-400 text-xs hover:underline">Remover</button>
                </div>
              )) : <p className="text-sm text-text-muted">Nenhum responsável.</p>}
              <button disabled={busy} onClick={() => addLink('parent')} className="text-accent-neon text-xs hover:underline mt-1">+ Adicionar responsável</button>

              <div className="text-xs text-text-muted mb-1 mt-3">Dependentes</div>
              {data.links?.dependents.length ? data.links.dependents.map((d) => (
                <div key={d.link_id} className="flex items-center justify-between text-sm py-1">
                  <span className="truncate">{d.full_name || d.email} <span className="text-text-muted">#{d.id}</span></span>
                  <button disabled={busy} onClick={() => removeLink('child', d.id)} className="text-red-400 text-xs hover:underline">Remover</button>
                </div>
              )) : <p className="text-sm text-text-muted">Nenhum dependente.</p>}
              <button disabled={busy} onClick={() => addLink('child')} className="text-accent-neon text-xs hover:underline mt-1">+ Adicionar dependente</button>
            </DetailSection>

            {/* Ações */}
            <div className="flex flex-wrap gap-2 pt-1">
              <button disabled={busy} onClick={onEdit} className="btn-secondary flex items-center gap-1 text-sm"><UserCog className="w-4 h-4" /> Editar</button>
              <button disabled={busy} onClick={resetPassword} className="btn-secondary flex items-center gap-1 text-sm"><KeyRound className="w-4 h-4" /> Resetar senha</button>
              {data.is_login_locked && (
                <button disabled={busy} onClick={unlockLogin} className="btn-secondary flex items-center gap-1 text-sm"><Unlock className="w-4 h-4" /> Desbloquear login</button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('pt-BR'); } catch { return iso; }
}

// ─── Confirm modal ────────────────────────────────────────────────────────────

const ConfirmModal: React.FC<{
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ title, message, onConfirm, onCancel }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
    <div className="bg-bg-card border border-border rounded-2xl w-full max-w-sm p-5 space-y-4">
      <h2 className="font-bold text-lg text-red-400">{title}</h2>
      <p className="text-sm text-text-secondary">{message}</p>
      <div className="flex gap-2">
        <button onClick={onCancel} className="btn-secondary flex-1">Cancelar</button>
        <button
          onClick={onConfirm}
          className="flex-1 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white font-semibold text-sm flex items-center justify-center gap-1 transition-colors"
        >
          <Trash2 className="w-4 h-4" /> Deletar
        </button>
      </div>
    </div>
  </div>
);

// ─── Shared components ────────────────────────────────────────────────────────

const Badge: React.FC<{ color: 'neon' | 'blue' | 'red' | 'green' | 'gray' | 'amber'; children: React.ReactNode }> = ({ color, children }) => {
  const cls = {
    neon:  'bg-accent-neon/10 text-accent-neon border-accent-neon/30',
    blue:  'bg-blue-500/10 text-blue-400 border-blue-500/30',
    red:   'bg-red-500/10 text-red-400 border-red-500/30',
    green: 'bg-green-500/10 text-green-400 border-green-500/30',
    gray:  'bg-gray-500/10 text-gray-400 border-gray-500/30',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  }[color];
  return <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${cls}`}>{children}</span>;
};

const StatCard: React.FC<{
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  accent?: boolean;
  warn?: boolean;
}> = ({ label, value, accent, warn }) => (
  <div className="card !p-3">
    <div className="text-[10px] text-text-muted uppercase">{label}</div>
    <div className={`text-xl font-bold mt-1 ${accent ? 'text-accent-neon' : warn ? 'text-status-closing' : ''}`}>
      {value}
    </div>
  </div>
);

const QueueSection: React.FC<{
  title: string;
  icon: React.ReactNode;
  items: TournamentEditionList[];
  emptyText: string;
}> = ({ title, icon, items, emptyText }) => (
  <section>
    <h2 className="font-semibold flex items-center gap-2 mb-2">{icon} {title}</h2>
    {items.length === 0 ? (
      <div className="card text-center py-6 text-sm text-text-muted">{emptyText}</div>
    ) : (
      <div className="space-y-2">
        {items.slice(0, 5).map((ed) => <TournamentCard key={ed.id} edition={ed} />)}
      </div>
    )}
  </section>
);

// ─── Sources tab ──────────────────────────────────────────────────────────────

interface DataSourceRow {
  id: number;
  organization: number;
  org_name: string;
  source_name: string;
  slug: string;
  connector_key: string;
  source_type: string;
  base_url: string;
  fetch_schedule_cron: string;
  priority: string;
  enabled: boolean;
  legal_notes: string;
}

const SourcesTab: React.FC = () => {
  const [sources, setSources] = useState<DataSourceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<DataSourceRow | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<DataSourceRow[]>('/api/admin-panel/sources/');
      setSources(res.data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function toggleEnabled(s: DataSourceRow) {
    try {
      const res = await api.patch<DataSourceRow>(`/api/admin-panel/sources/${s.id}/`, { enabled: !s.enabled });
      setSources((prev) => prev.map((r) => (r.id === s.id ? res.data : r)));
      toast.success(`Fonte ${res.data.enabled ? 'ativada' : 'desativada'}`);
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  async function saveEdit(form: Partial<DataSourceRow>) {
    if (!editing) return;
    try {
      const res = await api.patch<DataSourceRow>(`/api/admin-panel/sources/${editing.id}/`, form);
      setSources((prev) => prev.map((r) => (r.id === editing.id ? res.data : r)));
      setEditing(null);
      toast.success('Fonte atualizada');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  if (loading) return <div className="py-16 flex justify-center"><Loader2 className="w-8 h-8 text-accent-neon animate-spin" /></div>;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-text-secondary">Fontes de dados ({sources.length})</h2>
      {sources.map((s) => (
        <div key={s.id} className="card !p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">{s.source_name}</div>
              <div className="text-xs text-text-muted">{s.org_name} · Conector {s.connector_key} · prioridade {s.priority}</div>
              <div className="text-[11px] text-text-muted mt-0.5">Agendamento: {s.fetch_schedule_cron || '—'}</div>
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => toggleEnabled(s)}
                className={`text-xs px-2 py-1 rounded border ${s.enabled ? 'border-accent-neon text-accent-neon' : 'border-border-subtle text-text-muted'}`}
                title={s.enabled ? 'Desativar' : 'Ativar'}
              >
                {s.enabled ? <Shield className="w-3 h-3 inline" /> : <ShieldOff className="w-3 h-3 inline" />}
                <span className="ml-1">{s.enabled ? 'ativa' : 'inativa'}</span>
              </button>
              <button
                onClick={() => setEditing(s)}
                className="text-xs px-2 py-1 rounded border border-border-subtle text-text-muted hover:text-text-primary"
              >
                Editar
              </button>
            </div>
          </div>
          {s.legal_notes && <div className="text-[11px] text-text-muted italic">{s.legal_notes}</div>}
        </div>
      ))}

      {editing && (
        <SourceEditModal
          source={editing}
          onSave={saveEdit}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
};

const SourceEditModal: React.FC<{
  source: DataSourceRow;
  onSave: (form: Partial<DataSourceRow>) => void;
  onCancel: () => void;
}> = ({ source, onSave, onCancel }) => {
  const [cron, setCron] = useState(source.fetch_schedule_cron || '');
  const [priority, setPriority] = useState(source.priority || '');
  const [baseUrl, setBaseUrl] = useState(source.base_url || '');
  const [legalNotes, setLegalNotes] = useState(source.legal_notes || '');

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onCancel}>
      <div className="bg-bg-card rounded-xl p-4 max-w-md w-full space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-semibold">Editar fonte: {source.source_name}</h3>
          <button onClick={onCancel}><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-2">
          <div>
            <label className="text-xs text-text-secondary">Agendamento</label>
            <input className="input-base" value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 */6 * * *" />
          </div>
          <div>
            <label className="text-xs text-text-secondary">Prioridade</label>
            <select className="input-base" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="P0">P0</option>
              <option value="P1">P1</option>
              <option value="P2">P2</option>
              <option value="P3">P3</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-secondary">Link base</label>
            <input className="input-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-text-secondary">Notas legais</label>
            <textarea className="input-base" rows={2} value={legalNotes} onChange={(e) => setLegalNotes(e.target.value)} />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-secondary !py-2 !px-3 text-sm" onClick={onCancel}>Cancelar</button>
          <button
            className="btn-primary !py-2 !px-3 text-sm"
            onClick={() => onSave({
              fetch_schedule_cron: cron,
              priority,
              base_url: baseUrl,
              legal_notes: legalNotes,
            })}
          >Salvar</button>
        </div>
      </div>
    </div>
  );
};

// ─── Connectors tab ───────────────────────────────────────────────────────────

interface ConnectorRow {
  connector_key: string;
  enabled: boolean;
  source_name: string;
  organization: string;
  last_run_at: string | null;
  last_run_status: string | null;
  is_blocked: boolean;
  consecutive_failures: number;
  action: string;
}

const ConnectorsTab: React.FC = () => {
  const [rows, setRows] = useState<ConnectorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<any[]>([]);

  async function load() {
    setLoading(true);
    try {
      const [c, l] = await Promise.all([
        api.get<ConnectorRow[]>('/api/admin-panel/connector-status/'),
        api.get<any[]>('/api/admin-panel/execution-logs/?limit=20'),
      ]);
      setRows(c.data);
      setLogs(l.data);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  if (loading) return <div className="py-16 flex justify-center"><Loader2 className="w-8 h-8 text-accent-neon animate-spin" /></div>;

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-text-secondary">Conectores ({rows.length})</h2>
          <button onClick={load} className="btn-secondary !py-1.5 !px-2"><RefreshCcw className="w-3 h-3" /></button>
        </div>
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.connector_key} className="card !p-3 flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-semibold">{r.connector_key} · {r.organization}</div>
                <div className="text-xs text-text-muted">{r.source_name}</div>
                <div className="text-[11px] text-text-muted mt-0.5">
                  Último: {r.last_run_at ? new Date(r.last_run_at).toLocaleString('pt-BR') : '—'} ({r.last_run_status ? (RUN_STATUS_LABELS[r.last_run_status] ?? UNKNOWN_STATUS_LABEL) : '—'})
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Badge color={r.enabled ? 'green' : 'gray'}>{r.enabled ? 'ativa' : 'inativa'}</Badge>
                {r.is_blocked && <Badge color="red">bloqueado</Badge>}
                {r.consecutive_failures > 0 && (
                  <span className="text-[10px] text-status-closing">{r.consecutive_failures} falhas seguidas</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-text-secondary mb-2">Últimas execuções</h2>
        <div className="space-y-1.5">
          {logs.length === 0 && <div className="card text-center py-6 text-sm text-text-muted">Sem execuções recentes.</div>}
          {logs.map((l: any) => (
            <div key={l.id} className="card !p-2 text-xs flex items-center justify-between">
              <div>
                <span className="font-semibold">{l.service}</span>
                <span className="text-text-muted ml-2">{l.organization}</span>
                <span className="text-text-muted ml-2">{l.started_at ? new Date(l.started_at).toLocaleString('pt-BR') : ''}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge color={l.status === 'success' ? 'green' : l.status === 'partial' ? 'amber' : 'red'}>{RUN_STATUS_LABELS[l.status] ?? UNKNOWN_STATUS_LABEL}</Badge>
                <span className="text-text-muted">{l.editions_created}+ / {l.editions_updated}~</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Editions admin tab ───────────────────────────────────────────────────────

interface AdminEdition {
  id: number;
  title: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  data_confidence: string;
  is_manual_override: boolean;
  is_youth: boolean | null;
  is_published: boolean;
  official_source_url: string;
  source_name?: string;
  organization_short_name?: string;
  venue_city?: string;
  venue_state?: string;
}

type PublishedFilter = 'all' | 'published' | 'unpublished';

const EditionsAdminTab: React.FC = () => {
  const [items, setItems] = useState<AdminEdition[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [publishedFilter, setPublishedFilter] = useState<PublishedFilter>('all');

  async function load(q = '', filter: PublishedFilter = publishedFilter) {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page_size: 50 };
      if (q) params.q = q;
      if (filter === 'published') params.published = 'true';
      if (filter === 'unpublished') params.published = 'false';

      // Admin-only endpoint: includes unpublished items so admin can republish.
      const res = await api.get<{ count: number; results: AdminEdition[] }>(
        '/api/admin-panel/editions-list/',
        { params },
      );
      setItems(res.data.results);
    } catch (err) {
      toast.error(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [publishedFilter]);

  async function togglePublished(e: AdminEdition) {
    try {
      const res = await api.patch<AdminEdition>(`/api/admin-panel/editions/${e.id}/`, { is_published: !e.is_published });
      setItems((prev) => prev.map((it) => (it.id === e.id ? { ...it, is_published: res.data.is_published } : it)));
      toast.success(res.data.is_published ? 'Publicado' : 'Oculto');
    } catch (err) {
      toast.error(extractApiError(err));
    }
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          className="input-base pl-9"
          placeholder="Buscar torneio…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); }}
          onKeyDown={(e) => e.key === 'Enter' && load(search.trim())}
        />
      </div>

      <div className="flex gap-1 text-xs">
        {(['all', 'published', 'unpublished'] as PublishedFilter[]).map((f) => (
          <button
            key={f}
            onClick={() => setPublishedFilter(f)}
            className={`px-3 py-1.5 rounded border ${
              publishedFilter === f
                ? 'border-accent-neon text-accent-neon bg-accent-neon/10'
                : 'border-border-subtle text-text-muted hover:text-text-primary'
            }`}
          >
            {f === 'all' ? 'Todos' : f === 'published' ? 'Publicados' : 'Ocultos'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-10 flex justify-center"><Loader2 className="w-6 h-6 text-accent-neon animate-spin" /></div>
      ) : items.length === 0 ? (
        <div className="card text-center py-6 text-sm text-text-muted">Nenhum torneio.</div>
      ) : (
        <div className="space-y-2">
          {items.map((e) => (
            <div key={e.id} className="card !p-3 flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold truncate">{e.title}</div>
                <div className="text-xs text-text-muted">
                  {e.start_date || 'Sem data'} · {EDITION_STATUS_LABELS[e.status] ?? UNKNOWN_STATUS_LABEL} · {CONFIDENCE_LABELS[e.data_confidence] ?? 'Qualidade dos dados não informada'}
                  {e.organization_short_name && ` · ${e.organization_short_name}`}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {e.is_published === false && <Badge color="amber">oculto</Badge>}
                {e.is_manual_override && <Badge color="blue">override</Badge>}
                <button
                  onClick={() => togglePublished(e)}
                  className="text-xs px-2 py-1 rounded border border-border-subtle hover:text-text-primary"
                >
                  {e.is_published === false ? 'Publicar' : 'Ocultar'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Waitlist leads tab ─────────────────────────────────────────────────────────

interface WaitlistLeadsResponse {
  available: boolean;
  columns: string[];
  results: Record<string, unknown>[];
  count: number;
  detail?: string;
}

// Rótulos amigáveis para as colunas da tabela (fallback: humaniza o nome do banco).
const LEAD_LABELS: Record<string, string> = {
  id: 'ID', uuid: 'ID',
  email: 'E-mail', e_mail: 'E-mail',
  name: 'Nome', nome: 'Nome', full_name: 'Nome', fullname: 'Nome', first_name: 'Nome',
  last_name: 'Sobrenome', sobrenome: 'Sobrenome',
  phone: 'Telefone', telefone: 'Telefone', celular: 'Celular', whatsapp: 'WhatsApp',
  created_at: 'Criado em', inserted_at: 'Criado em', created: 'Criado em', createdat: 'Criado em',
  updated_at: 'Atualizado em', updatedat: 'Atualizado em',
  source: 'Origem', origem: 'Origem',
  city: 'Cidade', cidade: 'Cidade',
  state: 'Estado', estado: 'Estado', uf: 'UF',
  country: 'País', pais: 'País',
  role: 'Perfil', perfil: 'Perfil', tipo: 'Tipo',
  status: 'Status', message: 'Mensagem', mensagem: 'Mensagem',
  utm_source: 'UTM origem', utm_medium: 'UTM mídia', utm_campaign: 'UTM campanha',
  ip: 'IP', user_agent: 'Navegador',
  marketing_consent: 'Consentimento', consent: 'Consentimento',
};

const humanizeLeadLabel = (col: string): string => {
  const key = col.toLowerCase();
  if (LEAD_LABELS[key]) return LEAD_LABELS[key];
  return col
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

const isLeadDateCol = (col: string) => /(_at$|^created|^updated|date|data|criad|atualizad)/i.test(col);
const isLeadEmailCol = (col: string) => /e-?mail/i.test(col);
// Colunas que não devem ser exibidas na tabela de leads (ex.: preço, descontinuado).
const isHiddenLeadCol = (col: string) => /pre[çc]o|price|valor/i.test(col);

const formatLeadValue = (col: string, v: unknown): string => {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Sim' : 'Não';
  if (typeof v === 'object') return JSON.stringify(v);
  const s = String(v);
  if (isLeadDateCol(col)) {
    const d = new Date(s);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    }
  }
  return s;
};

const WaitlistLeadsTab: React.FC = () => {
  const [data, setData] = useState<WaitlistLeadsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<WaitlistLeadsResponse>('/api/admin-panel/waitlist-leads/', {
        params: { limit: 500 },
      });
      setData(res.data);
    } catch (e) {
      setError(extractApiError(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const visibleColumns = (data?.columns ?? []).filter((c) => !isHiddenLeadCol(c));

  if (loading) return <div className="card text-center py-8 text-text-muted text-sm">Carregando…</div>;
  if (error) return <div className="card text-center py-8 text-sm text-red-400">{error}</div>;
  if (!data) return null;

  if (!data.available) {
    return (
      <div className="card text-center py-10 space-y-2">
        <Database className="w-8 h-8 text-text-muted mx-auto" />
        <p className="text-sm font-medium">Leads indisponíveis</p>
        <p className="text-xs text-text-muted max-w-md mx-auto">
          {data.detail || 'Tabela tenfy_waitlist_leads não encontrada no banco.'}
        </p>
        <button onClick={load} className="btn-secondary !text-sm mt-2 inline-flex items-center gap-1.5">
          <RefreshCcw className="w-3.5 h-3.5" /> Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-base flex items-center gap-2">
          <Database className="w-4 h-4 text-accent-neon" />
          Inscritos — Waitlist
          <span className="text-xs font-medium text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full">{data.count}</span>
        </h2>
        <button onClick={load} className="btn-secondary !text-xs flex items-center gap-1.5">
          <RefreshCcw className="w-3.5 h-3.5" /> Atualizar
        </button>
      </div>

      {data.results.length === 0 ? (
        <div className="card text-center py-10 text-text-muted text-sm">Nenhum lead encontrado ainda.</div>
      ) : (
        <div className="card !p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-bg-elevated/70 border-b border-border">
                  <th className="px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-text-muted whitespace-nowrap">#</th>
                  {visibleColumns.map((c) => (
                    <th
                      key={c}
                      className="px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-text-muted whitespace-nowrap"
                    >
                      {humanizeLeadLabel(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.results.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/40 last:border-0 even:bg-bg-elevated/20 hover:bg-accent-neon/5 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-text-muted text-xs tabular-nums whitespace-nowrap">{i + 1}</td>
                    {visibleColumns.map((c) => {
                      const val = formatLeadValue(c, row[c]);
                      const isEmail = isLeadEmailCol(c) && val !== '—';
                      return (
                        <td
                          key={c}
                          className="px-4 py-2.5 align-middle whitespace-nowrap max-w-[320px] truncate"
                          title={val}
                        >
                          {isEmail ? (
                            <a href={`mailto:${val}`} className="text-accent-blue hover:underline">{val}</a>
                          ) : (
                            val
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.count > data.results.length && (
        <p className="text-xs text-text-muted text-center">
          Mostrando os {data.results.length} mais recentes de {data.count}.
        </p>
      )}
    </div>
  );
};
