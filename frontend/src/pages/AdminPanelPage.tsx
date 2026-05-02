import React, { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Database, Loader2, Link2,
  Play, RefreshCcw, Search, Shield, ShieldOff,
  Trash2, UserCog, X, BarChart2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts';
import api, { extractApiError } from '../services/api';
import { TournamentEditionList } from '../types';
import { TournamentCard } from '../components/TournamentCard';

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
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  email_verified: boolean;
  marketing_consent: boolean;
  created_at: string;
  last_login: string | null;
}

interface AdminStats {
  registrations: { date: string; registrations: number }[];
  users_by_role: { role: string; count: number }[];
  tournaments_by_status: { status: string; count: number }[];
  watchlist_by_status: { status: string; count: number }[];
  totals: { users: number; active_users: number; new_users_period: number };
}

type Tab = 'dashboard' | 'stats' | 'users' | 'sources' | 'connectors' | 'editions';

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

      {tab === 'dashboard'  && <DashboardTab />}
      {tab === 'stats'      && <StatsTab />}
      {tab === 'users'      && <UsersTab />}
      {tab === 'sources'    && <SourcesTab />}
      {tab === 'connectors' && <ConnectorsTab />}
      {tab === 'editions'   && <EditionsAdminTab />}
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
        <StatCard label="Baixa confiança" value={dash.counts.low_confidence} warn />
        <StatCard label="Sem URL oficial" value={dash.counts.missing_official_url} warn />
        <StatCard label="Execuções 24h" value={`${dash.ingestion.runs_24h} (${dash.ingestion.failed_24h} falhas)`} />
      </div>

      {queue && (
        <>
          <QueueSection title="Baixa confiança" icon={<AlertTriangle className="w-4 h-4 text-status-closing" />} items={queue.low_confidence} emptyText="Nenhuma edição com baixa confiança." />
          <QueueSection title="Sem link oficial" icon={<Link2 className="w-4 h-4 text-status-canceled" />} items={queue.missing_official_url} emptyText="Todas as edições possuem link oficial." />
          <QueueSection title="Alteradas recentemente" icon={<RefreshCcw className="w-4 h-4 text-accent-blue" />} items={queue.recently_changed} emptyText="Nenhuma alteração recente." />
        </>
      )}
    </div>
  );
};

// ─── Stats tab ────────────────────────────────────────────────────────────────

const CHART_COLORS = ['#39ff14', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];

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
              stroke="#39ff14"
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
              <XAxis dataKey="role" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} />
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
              <XAxis dataKey="status" tick={{ fontSize: 9, fill: 'rgb(var(--text-muted))' }} />
              <YAxis tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Torneios" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card !p-4 space-y-3 md:col-span-2">
          <h3 className="text-sm font-semibold text-text-secondary">Watchlist por status</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.watchlist_by_status} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} allowDecimals={false} />
              <YAxis type="category" dataKey="status" tick={{ fontSize: 10, fill: 'rgb(var(--text-muted))' }} width={60} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Itens" fill="#f59e0b" radius={[0, 4, 4, 0]} />
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

const UsersTab: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<AdminUser | null>(null);
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
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
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
              <div className="w-9 h-9 rounded-full bg-bg-surface flex items-center justify-center shrink-0 text-sm font-bold text-accent-neon uppercase">
                {(u.full_name || u.email)[0]}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm truncate">{u.full_name || '—'}</span>
                  {u.is_superuser && <Badge color="neon">Superadmin</Badge>}
                  {u.is_staff && !u.is_superuser && <Badge color="blue">Staff</Badge>}
                  {!u.is_active && <Badge color="red">Inativo</Badge>}
                </div>
                <div className="text-xs text-text-muted truncate">{u.email}</div>
                <div className="text-xs text-text-muted">{ROLE_LABELS[u.role] ?? u.role}</div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
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
        <p className="text-xs text-text-muted">{user.email}</p>
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
              <div className="text-xs text-text-muted">{s.org_name} · {s.connector_key} · {s.priority}</div>
              <div className="text-[11px] text-text-muted mt-0.5">cron: {s.fetch_schedule_cron || '—'}</div>
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
            <label className="text-xs text-text-secondary">Cron</label>
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
            <label className="text-xs text-text-secondary">Base URL</label>
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
                  Último: {r.last_run_at ? new Date(r.last_run_at).toLocaleString('pt-BR') : '—'} ({r.last_run_status || '—'})
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
                <Badge color={l.status === 'success' ? 'green' : l.status === 'partial' ? 'amber' : 'red'}>{l.status}</Badge>
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
                  {e.start_date || 'sem data'} · {e.status} · confiança {e.data_confidence}
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
