import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Pressable, ScrollView, TextInput, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import api, { extractApiError } from '../../services/api';

type Props = NativeStackScreenProps<MainStackParamList, 'AdminPanel'>;
type Tab = 'dashboard' | 'review' | 'sources' | 'stats' | 'users' | 'connectors';

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
  ingestion: { runs_24h: number; failed_24h: number; partial_24h?: number };
  alerts: { total_7d: number; failed_7d: number };
  audit: { actions_24h: number };
}

interface AdminStats {
  registrations: { date: string; registrations: number }[];
  users_by_role: { role: string; count: number }[];
  tournaments_by_status: { status: string; count: number }[];
  totals: { users: number; active_users: number; new_users_period: number };
}

interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  phone?: string;
  role: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  email_verified: boolean;
  marketing_consent?: boolean;
  created_at?: string;
  last_login?: string;
}

interface ExecutionLog {
  id: number;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  status: string;
  service: string;
  organization: string;
  editions_found: number;
  editions_created: number;
  editions_updated: number;
  error: string;
}

const ROLE_LABELS: Record<string, string> = {
  player: 'Jogador',
  coach: 'Treinador',
  parent: 'Pai/Resp.',
  admin: 'Admin',
};

const STATUS_COLORS: Record<string, string> = {
  success: '#39ff14',
  failed: '#ef4444',
  partial: '#f59e0b',
  running: '#3b82f6',
};

const STATUS_LABELS: Record<string, string> = {
  unknown:       'Desconhecido',
  announced:     'Anunciado',
  open:          'Aberto',
  closing_soon:  'Fechando',
  closed:        'Encerrado',
  draws_published: 'Chaves',
  in_progress:   'Em andamento',
  finished:      'Finalizado',
  canceled:      'Cancelado',
};

const EXECUTION_STATUS_LABELS: Record<string, string> = {
  running: 'Executando',
  success: 'Sucesso',
  failed:  'Falhou',
  partial: 'Parcial',
};

const DATA_CONFIDENCE_LABELS: Record<string, string> = {
  low: 'Baixa',
  med: 'Média',
  medium: 'Média',
  high: 'Alta',
};

export function AdminPanelScreen({ navigation }: Props) {
  const { colors } = useTheme();
  const [tab, setTab] = useState<Tab>('dashboard');

  const tabs: { key: Tab; label: string }[] = [
    { key: 'dashboard',  label: 'Dashboard' },
    { key: 'connectors', label: 'Conectores' },
    { key: 'review',     label: 'Curadoria' },
    { key: 'sources',    label: 'Fontes' },
    { key: 'stats',      label: 'Estatísticas' },
    { key: 'users',      label: 'Usuários' },
  ];

  return (
    <Screen scroll={false}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View>
          <AppText variant="title">Painel admin</AppText>
          <AppText variant="muted">Curadoria, ingestão e usuários</AppText>
        </View>
      </View>

      <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.borderSubtle, marginBottom: 8 }}>
        {tabs.map((t) => (
          <Pressable
            key={t.key}
            onPress={() => setTab(t.key)}
            style={{ paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: tab === t.key ? colors.accentNeon : 'transparent', marginBottom: -1 }}
          >
            <AppText variant="caption" style={{ color: tab === t.key ? colors.accentNeon : colors.textMuted, fontWeight: tab === t.key ? '700' : '400' }}>
              {t.label}
            </AppText>
          </Pressable>
        ))}
      </View>

      {tab === 'dashboard'  && <DashboardTab />}
      {tab === 'connectors' && <ConnectorsTab />}
      {tab === 'review'     && <ReviewTab />}
      {tab === 'sources'    && <SourcesTab />}
      {tab === 'stats'      && <StatsTab />}
      {tab === 'users'      && <UsersTab />}
    </Screen>
  );
}

// ─── Dashboard Tab ─────────────────────────────────────────────────────────────

function DashboardTab() {
  const { colors } = useTheme();
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [logs, setLogs] = useState<ExecutionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [dashRes, logsRes] = await Promise.all([
        api.get<Dashboard>('/api/admin-panel/dashboard/'),
        api.get<ExecutionLog[]>('/api/admin-panel/execution-logs/?limit=30'),
      ]);
      setDash(dashRes.data);
      setLogs(logsRes.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar dashboard', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  async function runIngestion() {
    setRunning(true);
    try {
      await api.post('/api/ingestion/runs/run-all/');
      Toast.show({ type: 'success', text1: 'Ingestão disparada!' });
      setTimeout(load, 3000);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao iniciar ingestão', text2: extractApiError(err) });
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <LoadingBlock />;
  if (!dash) return <EmptyState title="Não foi possível carregar o dashboard." />;

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100, gap: 14 }}>
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
        <Button title="Atualizar" variant="secondary" onPress={load} />
        <Button title={running ? 'Ingerindo...' : 'Ingerir agora'} onPress={runIngestion} loading={running} />
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        <StatCard label="Torneios"    value={dash.counts.tournaments_total}        colors={colors} />
        <StatCard label="Abertos"     value={dash.counts.tournaments_open}         accent colors={colors} />
        <StatCard label="Fechando"    value={dash.counts.tournaments_closing_soon} warn colors={colors} />
        <StatCard label="Fontes"      value={`${dash.counts.data_sources_enabled}/${dash.counts.data_sources_total}`} colors={colors} />
        <StatCard label="Validações manuais" value={dash.counts.manual_overrides}  colors={colors} />
        <StatCard label="Baixa qualidade" value={dash.counts.low_confidence}        warn colors={colors} />
        <StatCard label="Sem link oficial" value={dash.counts.missing_official_url} warn colors={colors} />
        <StatCard label="Exec. 24h"   value={`${dash.ingestion.runs_24h} (${dash.ingestion.failed_24h} falhas)`} colors={colors} />
      </View>

      <SectionHeader title="Alertas (7d)" />
      <Card>
        <AppText variant="body">Total: <AppText variant="body" style={{ fontWeight: '700' }}>{dash.alerts.total_7d}</AppText></AppText>
        <AppText variant="caption">Falhas: {dash.alerts.failed_7d}</AppText>
      </Card>

      <SectionHeader title="Auditoria (24h)" />
      <Card>
        <AppText variant="body">Ações: <AppText variant="body" style={{ fontWeight: '700' }}>{dash.audit.actions_24h}</AppText></AppText>
      </Card>

      {/* Execution Logs */}
      <Pressable
        onPress={() => setShowLogs(!showLogs)}
        style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, marginBottom: 4 }}
      >
        <AppText variant="section">Logs de execução</AppText>
        <Ionicons name={showLogs ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
      </Pressable>

      {showLogs && (
        logs.length === 0 ? (
          <Card><AppText variant="muted">Nenhuma execução registrada.</AppText></Card>
        ) : (
          logs.map((log) => (
            <View key={log.id} style={{ backgroundColor: colors.bgCard, borderRadius: 12, padding: 12, marginBottom: 6, borderLeftWidth: 3, borderLeftColor: STATUS_COLORS[log.status] ?? colors.borderSubtle }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <View style={{ flex: 1 }}>
                  <AppText variant="body" style={{ fontWeight: '600', fontSize: 12 }}>{log.service}</AppText>
                  <AppText variant="muted" style={{ fontSize: 10 }}>{log.organization}</AppText>
                </View>
                <View style={{ alignItems: 'flex-end', gap: 2 }}>
                  <View style={{ backgroundColor: `${STATUS_COLORS[log.status] ?? colors.borderSubtle}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                    <AppText variant="muted" style={{ fontSize: 10, color: STATUS_COLORS[log.status] ?? colors.textMuted, fontWeight: '700' }}>{EXECUTION_STATUS_LABELS[log.status] ?? log.status.toUpperCase()}</AppText>
                  </View>
                  {log.duration_seconds != null && (
                    <AppText variant="muted" style={{ fontSize: 9 }}>{log.duration_seconds}s</AppText>
                  )}
                </View>
              </View>
              {log.started_at && (
                <AppText variant="muted" style={{ fontSize: 10, marginTop: 4 }}>
                  {new Date(log.started_at).toLocaleString('pt-BR')}
                </AppText>
              )}
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                {log.editions_found > 0 && <AppText variant="muted" style={{ fontSize: 10 }}>encontrados: {log.editions_found}</AppText>}
                {log.editions_created > 0 && <AppText variant="muted" style={{ fontSize: 10, color: '#39ff14' }}>+{log.editions_created} novos</AppText>}
                {log.editions_updated > 0 && <AppText variant="muted" style={{ fontSize: 10, color: '#3b82f6' }}>~{log.editions_updated} atualizados</AppText>}
              </View>
              {log.error ? (
                <AppText variant="muted" style={{ fontSize: 10, color: '#ef4444', marginTop: 4 }} numberOfLines={3}>
                  {log.error}
                </AppText>
              ) : null}
            </View>
          ))
        )
      )}
    </ScrollView>
  );
}

// ─── Stats Tab ─────────────────────────────────────────────────────────────────

function StatsTab() {
  const { colors } = useTheme();
  const [data, setData] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  async function load(d = days) {
    setLoading(true);
    try {
      const res = await api.get<AdminStats>(`/api/admin-panel/stats/?days=${d}`);
      setData(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar estatísticas', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <LoadingBlock />;
  if (!data) return <EmptyState title="Sem dados de estatísticas." />;

  const maxReg = Math.max(...data.registrations.map((r) => r.registrations), 1);
  const maxRole = Math.max(...data.users_by_role.map((r) => r.count), 1);
  const maxStatus = Math.max(...data.tournaments_by_status.map((r) => r.count), 1);

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 16, paddingBottom: 100 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {[7, 30, 90].map((d) => (
          <Pressable key={d} onPress={() => { setDays(d); load(d); }}
            style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, borderWidth: 1, borderColor: days === d ? colors.accentNeon : colors.borderSubtle, backgroundColor: days === d ? `${colors.accentNeon}15` : 'transparent' }}>
            <AppText variant="caption" style={{ color: days === d ? colors.accentNeon : colors.textMuted }}>{d}d</AppText>
          </Pressable>
        ))}
      </View>

      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 16, padding: 14, alignItems: 'center' }}>
          <AppText variant="muted" style={{ fontSize: 10 }}>USUÁRIOS</AppText>
          <AppText variant="title" style={{ color: colors.accentNeon }}>{data.totals.users}</AppText>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 16, padding: 14, alignItems: 'center' }}>
          <AppText variant="muted" style={{ fontSize: 10 }}>ATIVOS</AppText>
          <AppText variant="title">{data.totals.active_users}</AppText>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 16, padding: 14, alignItems: 'center' }}>
          <AppText variant="muted" style={{ fontSize: 10 }}>NOVOS ({days}d)</AppText>
          <AppText variant="title" style={{ color: colors.accentBlue }}>{data.totals.new_users_period}</AppText>
        </View>
      </View>

      <Card>
        <AppText variant="body" style={{ fontWeight: '600', marginBottom: 12 }}>Cadastros por dia</AppText>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 80 }}>
            {data.registrations.slice(-20).map((r) => (
              <View key={r.date} style={{ alignItems: 'center', gap: 2 }}>
                <View style={{ width: 14, height: Math.max(4, (r.registrations / maxReg) * 64), backgroundColor: colors.accentNeon, borderRadius: 3 }} />
                <AppText variant="muted" style={{ fontSize: 8 }}>{r.date.slice(5)}</AppText>
              </View>
            ))}
          </View>
        </ScrollView>
      </Card>

      <Card>
        <AppText variant="body" style={{ fontWeight: '600', marginBottom: 12 }}>Usuários por perfil</AppText>
        {data.users_by_role.map((r, i) => {
          const barColors = ['#39ff14', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];
          return (
            <View key={r.role} style={{ marginBottom: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                <AppText variant="caption">{ROLE_LABELS[r.role] ?? r.role}</AppText>
                <AppText variant="caption" style={{ fontWeight: '700' }}>{r.count}</AppText>
              </View>
              <View style={{ height: 6, backgroundColor: `${barColors[i % barColors.length]}30`, borderRadius: 3 }}>
                <View style={{ height: 6, width: `${(r.count / maxRole) * 100}%`, backgroundColor: barColors[i % barColors.length], borderRadius: 3 }} />
              </View>
            </View>
          );
        })}
      </Card>

      <Card>
        <AppText variant="body" style={{ fontWeight: '600', marginBottom: 12 }}>Torneios por status</AppText>
        {data.tournaments_by_status.map((r) => (
          <View key={r.status} style={{ marginBottom: 8 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
              <AppText variant="caption">{STATUS_LABELS[r.status] ?? r.status}</AppText>
              <AppText variant="caption" style={{ fontWeight: '700' }}>{r.count}</AppText>
            </View>
            <View style={{ height: 6, backgroundColor: `${colors.accentBlue}30`, borderRadius: 3 }}>
              <View style={{ height: 6, width: `${(r.count / maxStatus) * 100}%`, backgroundColor: colors.accentBlue, borderRadius: 3 }} />
            </View>
          </View>
        ))}
      </Card>
    </ScrollView>
  );
}

// ─── Users Tab ─────────────────────────────────────────────────────────────────

function UsersTab() {
  const { colors } = useTheme();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<AdminUser | null>(null);

  async function load(q = '') {
    setLoading(true);
    try {
      const res = await api.get<AdminUser[]>('/api/admin-panel/users/', { params: q ? { q } : {} });
      setUsers(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar usuários', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function handleDelete(user: AdminUser) {
    Alert.alert(
      'Remover usuário',
      `Tem certeza que deseja remover ${user.full_name || user.email}? Esta ação não pode ser desfeita.`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/api/admin-panel/users/${user.id}/`);
              setUsers((prev) => prev.filter((u) => u.id !== user.id));
              Toast.show({ type: 'success', text1: `${user.email} removido.` });
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Erro ao remover usuário', text2: extractApiError(err) });
            }
          },
        },
      ],
    );
  }

  function onSaved(updated: AdminUser) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    setEditing(null);
  }

  return (
    <View style={{ flex: 1 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bgCard, borderRadius: 12, paddingHorizontal: 12, marginBottom: 12, borderWidth: 1, borderColor: colors.borderSubtle }}>
        <Ionicons name="search-outline" size={16} color={colors.textMuted} />
        <TextInput
          style={{ flex: 1, paddingVertical: 10, paddingLeft: 8, color: colors.textPrimary, fontSize: 14 }}
          placeholder="Buscar por e-mail ou nome..."
          placeholderTextColor={colors.textMuted}
          value={search}
          onChangeText={(v) => { setSearch(v); load(v); }}
        />
      </View>

      {loading ? <LoadingBlock /> : users.length === 0 ? <EmptyState title="Nenhum usuário encontrado." /> : (
        <ScrollView showsVerticalScrollIndicator={false}>
          {users.map((u) => (
            <View key={u.id} style={{ backgroundColor: colors.bgCard, borderRadius: 16, padding: 12, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.accentNeon}20`, alignItems: 'center', justifyContent: 'center' }}>
                <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700' }}>
                  {(u.full_name || u.email)[0].toUpperCase()}
                </AppText>
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <AppText variant="body" style={{ fontWeight: '600', fontSize: 13 }}>{u.full_name || '—'}</AppText>
                  {u.is_superuser && <View style={{ backgroundColor: `${colors.accentNeon}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}><AppText variant="muted" style={{ fontSize: 10, color: colors.accentNeon }}>Super</AppText></View>}
                  {u.is_staff && !u.is_superuser && <View style={{ backgroundColor: `${colors.accentBlue}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}><AppText variant="muted" style={{ fontSize: 10, color: colors.accentBlue }}>Staff</AppText></View>}
                  {!u.is_active && <View style={{ backgroundColor: '#ef444420', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}><AppText variant="muted" style={{ fontSize: 10, color: '#ef4444' }}>Inativo</AppText></View>}
                </View>
                <AppText variant="muted" style={{ fontSize: 11 }}>{u.email}</AppText>
                <AppText variant="muted" style={{ fontSize: 11 }}>{ROLE_LABELS[u.role] ?? u.role}</AppText>
              </View>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                <Pressable onPress={() => setEditing(u)} style={{ padding: 6, borderRadius: 8, backgroundColor: colors.bgElevated }}>
                  <Ionicons name="create-outline" size={16} color={colors.textMuted} />
                </Pressable>
                {!u.is_superuser && (
                  <Pressable onPress={() => handleDelete(u)} style={{ padding: 6, borderRadius: 8, backgroundColor: colors.bgElevated }}>
                    <Ionicons name="trash-outline" size={16} color="#ef4444" />
                  </Pressable>
                )}
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      {/* Fix 2: Use proper Modal instead of absolute-positioned overlay */}
      <Modal
        visible={!!editing}
        transparent
        animationType="fade"
        onRequestClose={() => setEditing(null)}
      >
        {editing && <EditUserModal user={editing} onClose={() => setEditing(null)} onSaved={onSaved} />}
      </Modal>
    </View>
  );
}

// ─── Edit User Modal — Fix 13: full fields + confirmation dialogs ─────────────

function EditUserModal({ user, onClose, onSaved }: { user: AdminUser; onClose: () => void; onSaved: (u: AdminUser) => void }) {
  const { colors } = useTheme();
  const [form, setForm] = useState({
    full_name: user.full_name,
    role: user.role,
    is_active: user.is_active,
    is_staff: user.is_staff,
    marketing_consent: user.marketing_consent ?? false,
  });
  const [saving, setSaving] = useState(false);

  const roles = ['player', 'coach', 'parent', 'admin'];

  function confirmSave() {
    const changes: string[] = [];
    if (form.role !== user.role) changes.push(`Perfil: ${ROLE_LABELS[user.role]} → ${ROLE_LABELS[form.role]}`);
    if (form.is_active !== user.is_active) changes.push(`Status: ${user.is_active ? 'Ativo' : 'Inativo'} → ${form.is_active ? 'Ativo' : 'Inativo'}`);
    if (form.is_staff !== user.is_staff) changes.push(`Staff: ${user.is_staff ? 'Sim' : 'Não'} → ${form.is_staff ? 'Sim' : 'Não'}`);

    if (changes.length > 0) {
      Alert.alert(
        'Confirmar alterações',
        `Você está prestes a alterar:\n\n${changes.join('\n')}\n\nTem certeza?`,
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Confirmar', style: 'default', onPress: save },
        ],
      );
    } else {
      save();
    }
  }

  async function save() {
    setSaving(true);
    try {
      const res = await api.patch<AdminUser>(`/api/admin-panel/users/${user.id}/`, form);
      Toast.show({ type: 'success', text1: 'Usuário atualizado.' });
      onSaved(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao salvar', text2: extractApiError(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: 20 }}>
      <View style={{ backgroundColor: colors.bgCard, borderRadius: 20, padding: 20, width: '100%', maxWidth: 380 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <AppText variant="body" style={{ fontWeight: '700', fontSize: 16 }}>Editar usuário</AppText>
          <Pressable onPress={onClose} hitSlop={8}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
        </View>
        <AppText variant="muted" style={{ fontSize: 12, marginBottom: 16 }}>{user.email}</AppText>

        {/* Name */}
        <AppText variant="caption" style={{ marginBottom: 4 }}>Nome completo</AppText>
        <TextInput
          style={{ backgroundColor: colors.bgElevated, borderRadius: 10, padding: 10, color: colors.textPrimary, marginBottom: 12, fontSize: 14 }}
          value={form.full_name}
          onChangeText={(v) => setForm({ ...form, full_name: v })}
          placeholderTextColor={colors.textMuted}
        />

        {/* Role */}
        <AppText variant="caption" style={{ marginBottom: 6 }}>Perfil</AppText>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          {roles.map((r) => (
            <Pressable
              key={r}
              onPress={() => setForm({ ...form, role: r })}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: form.role === r ? colors.accentNeon : colors.bgElevated }}
            >
              <AppText variant="caption" style={{ color: form.role === r ? colors.bgBase : colors.textSecondary }}>{ROLE_LABELS[r]}</AppText>
            </Pressable>
          ))}
        </View>

        {/* Account status + staff */}
        <AppText variant="caption" style={{ marginBottom: 6 }}>Conta</AppText>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
          <Pressable onPress={() => setForm({ ...form, is_active: !form.is_active })}
            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: colors.bgElevated, borderRadius: 10 }}>
            <Ionicons name={form.is_active ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={form.is_active ? colors.accentNeon : colors.textMuted} />
            <AppText variant="caption">Conta ativa</AppText>
          </Pressable>
          {!user.is_superuser && (
            <Pressable onPress={() => setForm({ ...form, is_staff: !form.is_staff })}
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: colors.bgElevated, borderRadius: 10 }}>
              <Ionicons name={form.is_staff ? 'shield-checkmark' : 'shield-outline'} size={18} color={form.is_staff ? colors.accentBlue : colors.textMuted} />
              <AppText variant="caption">Acesso admin</AppText>
            </Pressable>
          )}
        </View>

        {/* Info (read-only) */}
        <View style={{ backgroundColor: colors.bgElevated, borderRadius: 10, padding: 10, marginBottom: 16, gap: 4 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <AppText variant="muted" style={{ fontSize: 11 }}>E-mail verificado</AppText>
            <Ionicons name={user.email_verified ? 'checkmark-circle' : 'close-circle'} size={14} color={user.email_verified ? '#39ff14' : '#ef4444'} />
          </View>
          {user.created_at && (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <AppText variant="muted" style={{ fontSize: 11 }}>Cadastrado em</AppText>
              <AppText variant="muted" style={{ fontSize: 11 }}>{new Date(user.created_at).toLocaleDateString('pt-BR')}</AppText>
            </View>
          )}
          {user.last_login && (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <AppText variant="muted" style={{ fontSize: 11 }}>Último login</AppText>
              <AppText variant="muted" style={{ fontSize: 11 }}>{new Date(user.last_login).toLocaleDateString('pt-BR')}</AppText>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Button title="Cancelar" variant="secondary" onPress={onClose} />
          <Button title="Salvar" onPress={confirmSave} loading={saving} />
        </View>
      </View>
    </View>
  );
}

// ─── Connectors Tab ───────────────────────────────────────────────────────────

interface ConnectorStatus {
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

interface ManualEditionForm {
  title: string;
  circuit: string;
  start_date: string;
  end_date: string;
  entry_close_at: string;
  official_source_url: string;
  venue_city: string;
  venue_state: string;
  status: string;
}

function ConnectorsTab() {
  const { colors } = useTheme();
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<ManualEditionForm>({
    title: '', circuit: 'COSAT', start_date: '', end_date: '',
    entry_close_at: '', official_source_url: '', venue_city: '', venue_state: '',
    status: 'open',
  });

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<ConnectorStatus[]>('/api/admin-panel/connector-status/');
      setConnectors(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar conectores', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function unblockConnector(key: string) {
    // Trigger a forced run which will reset the circuit if successful
    try {
      const source = connectors.find(c => c.connector_key === key);
      if (!source) return;
      Toast.show({ type: 'info', text1: 'Tentando reconectar...' });
      await api.post('/api/ingestion/runs/run-all/');
      setTimeout(load, 3000);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro', text2: extractApiError(err) });
    }
  }

  async function saveManual() {
    if (!form.title.trim()) { Alert.alert('Erro', 'Título obrigatório.'); return; }
    if (!form.start_date) { Alert.alert('Erro', 'Data de início obrigatória.'); return; }
    setSaving(true);
    try {
      await api.post('/api/admin-panel/editions/', form);
      Toast.show({ type: 'success', text1: 'Torneio criado com sucesso!' });
      setShowForm(false);
      setForm({ title: '', circuit: 'COSAT', start_date: '', end_date: '', entry_close_at: '', official_source_url: '', venue_city: '', venue_state: '', status: 'open' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao criar torneio', text2: extractApiError(err) });
    } finally {
      setSaving(false);
    }
  }

  const blocked = connectors.filter(c => c.is_blocked || (!c.enabled && c.consecutive_failures > 0));
  const healthy = connectors.filter(c => !c.is_blocked && (c.enabled || c.consecutive_failures === 0));

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100 }}>
      <Button title="Atualizar" variant="secondary" onPress={load} style={{ marginBottom: 12 }} />

      {/* Blocked connectors */}
      {blocked.length > 0 && (
        <View style={{ backgroundColor: '#ef444418', borderRadius: 14, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: '#ef444444' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ionicons name="warning" size={18} color="#ef4444" />
            <AppText variant="body" style={{ fontWeight: '700', color: '#ef4444' }}>
              {blocked.length} conector{blocked.length > 1 ? 'es' : ''} bloqueado{blocked.length > 1 ? 's' : ''}
            </AppText>
          </View>
          {blocked.map((c) => (
            <View key={c.connector_key} style={{ backgroundColor: colors.bgCard, borderRadius: 10, padding: 12, marginBottom: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View>
                  <AppText variant="body" style={{ fontWeight: '700', fontSize: 13 }}>{c.organization} ({c.connector_key})</AppText>
                  <AppText variant="muted" style={{ fontSize: 11 }}>
                    {c.consecutive_failures} falhas consecutivas
                    {c.last_run_at ? ` • Último: ${new Date(c.last_run_at).toLocaleDateString('pt-BR')}` : ''}
                  </AppText>
                </View>
                <Pressable onPress={() => unblockConnector(c.connector_key)}
                  style={{ backgroundColor: `${colors.accentBlue}20`, padding: 6, borderRadius: 8 }}>
                  <Ionicons name="refresh" size={16} color={colors.accentBlue} />
                </Pressable>
              </View>
            </View>
          ))}
          <AppText variant="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Enquanto bloqueados, crie os torneios manualmente abaixo.
          </AppText>
        </View>
      )}

      {/* Healthy connectors */}
      <AppText variant="section" style={{ marginBottom: 8 }}>Conectores ativos</AppText>
      {loading ? <AppText variant="muted">Carregando...</AppText> : healthy.length === 0 ? (
        <Card>
          <AppText variant="body" style={{ fontWeight: '700' }}>Nenhum conector ativo encontrado.</AppText>
          <AppText variant="muted">Quando fontes forem cadastradas ou conectores forem habilitados, eles aparecerão aqui.</AppText>
        </Card>
      ) : healthy.map((c) => (
        <View key={c.connector_key} style={{ backgroundColor: colors.bgCard, borderRadius: 12, padding: 12, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.enabled ? '#39ff14' : '#6b7280' }} />
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontWeight: '600', fontSize: 13 }}>{c.organization}</AppText>
            <AppText variant="muted" style={{ fontSize: 10 }}>{c.connector_key} • {c.last_run_status || 'nunca executado'}</AppText>
          </View>
          {c.last_run_at && (
            <AppText variant="muted" style={{ fontSize: 10 }}>{new Date(c.last_run_at).toLocaleDateString('pt-BR')}</AppText>
          )}
        </View>
      ))}

      {/* Manual entry form */}
      <View style={{ marginTop: 16 }}>
        <Pressable
          onPress={() => setShowForm(!showForm)}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.bgCard, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.borderSubtle }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="add-circle-outline" size={20} color={colors.accentNeon} />
            <AppText variant="body" style={{ fontWeight: '700' }}>Adicionar torneio manualmente</AppText>
          </View>
          <Ionicons name={showForm ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
        </Pressable>

        {showForm && (
          <View style={{ backgroundColor: colors.bgCard, borderRadius: 12, padding: 16, marginTop: 4, gap: 10 }}>
            <AppText variant="caption" style={{ color: colors.textMuted, fontSize: 11 }}>
              Use para adicionar torneios COSAT/ITF/UTR quando o conector estiver bloqueado.
            </AppText>

            {[
              { label: 'Título do torneio *', key: 'title', placeholder: 'Ex: Copa COSAT Juvenil 2026' },
              { label: 'Link oficial', key: 'official_source_url', placeholder: 'https://...' },
              { label: 'Cidade', key: 'venue_city', placeholder: 'São Paulo' },
              { label: 'Estado (UF)', key: 'venue_state', placeholder: 'SP', maxLength: 2 },
              { label: 'Data de início (AAAA-MM-DD) *', key: 'start_date', placeholder: '2026-06-01' },
              { label: 'Data de fim (AAAA-MM-DD)', key: 'end_date', placeholder: '2026-06-07' },
              { label: 'Prazo de inscrição (AAAA-MM-DD)', key: 'entry_close_at', placeholder: '2026-05-25' },
            ].map(({ label, key, placeholder, maxLength }) => (
              <View key={key}>
                <AppText variant="caption" style={{ marginBottom: 4, fontSize: 12 }}>{label}</AppText>
                <TextInput
                  style={{ backgroundColor: colors.bgElevated, borderRadius: 8, padding: 10, color: colors.textPrimary, fontSize: 13 }}
                  placeholder={placeholder}
                  placeholderTextColor={colors.textMuted}
                  value={(form as any)[key]}
                  onChangeText={(v) => setForm({ ...form, [key]: maxLength ? v.slice(0, maxLength).toUpperCase() : v })}
                  autoCapitalize="none"
                  maxLength={maxLength}
                />
              </View>
            ))}

            <View>
              <AppText variant="caption" style={{ marginBottom: 4, fontSize: 12 }}>Circuito</AppText>
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                {['COSAT', 'ITF', 'UTR', 'CBT', 'FPT', 'Outro'].map((c) => (
                  <Pressable key={c} onPress={() => setForm({ ...form, circuit: c })}
                    style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: form.circuit === c ? colors.accentNeon : colors.bgElevated }}>
                    <AppText variant="caption" style={{ color: form.circuit === c ? colors.bgBase : colors.textSecondary, fontWeight: '600' }}>{c}</AppText>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
              <Button title="Cancelar" variant="secondary" onPress={() => setShowForm(false)} />
              <Button title="Criar torneio" onPress={saveManual} loading={saving} />
            </View>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

// ─── Review Tab ───────────────────────────────────────────────────────────────

interface ReviewSection {
  low_confidence: ReviewEdition[];
  missing_official_url: ReviewEdition[];
  recently_changed: ReviewEdition[];
}
interface ReviewEdition {
  id: number;
  title: string;
  status: string;
  start_date: string | null;
  data_confidence: string;
  official_source_url: string;
  is_manual_override: boolean;
}

function ReviewTab() {
  const { colors } = useTheme();
  const [data, setData] = useState<ReviewSection | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editUrl, setEditUrl] = useState('');
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<ReviewSection>('/api/admin-panel/review-queue/');
      setData(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar fila', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function saveUrl(id: number) {
    setSaving(true);
    try {
      await api.patch(`/api/admin-panel/editions/${id}/`, { official_source_url: editUrl });
      Toast.show({ type: 'success', text1: 'URL atualizada.' });
      setEditingId(null);
      await load();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao salvar', text2: extractApiError(err) });
    } finally {
      setSaving(false);
    }
  }

  async function markHighConfidence(id: number) {
    try {
      await api.patch(`/api/admin-panel/editions/${id}/`, { data_confidence: 'high', is_manual_override: true });
      Toast.show({ type: 'success', text1: 'Qualidade dos dados atualizada.' });
      await load();
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro', text2: extractApiError(err) });
    }
  }

  if (loading) return <LoadingBlock />;
  if (!data) return <EmptyState title="Nenhum dado disponível." />;

  const sections: { key: keyof ReviewSection; label: string; color: string }[] = [
    { key: 'low_confidence', label: 'Baixa qualidade dos dados', color: '#ef4444' },
    { key: 'missing_official_url', label: 'Sem link oficial', color: '#f59e0b' },
    { key: 'recently_changed', label: 'Recentemente alterados', color: colors.accentBlue },
  ];

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100 }}>
      <Button title="Atualizar" variant="secondary" onPress={load} style={{ marginBottom: 12 }} />
      {sections.map((sec) => {
        const items = data[sec.key];
        if (!items.length) return null;
        return (
          <View key={sec.key} style={{ marginBottom: 16 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: sec.color }} />
              <AppText variant="body" style={{ fontWeight: '700', color: sec.color }}>{sec.label} ({items.length})</AppText>
            </View>
            {items.map((ed) => (
              <View key={ed.id} style={{ backgroundColor: colors.bgCard, borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: colors.borderSubtle }}>
                <AppText variant="body" style={{ fontWeight: '600', fontSize: 13, marginBottom: 4 }} numberOfLines={2}>{ed.title}</AppText>
                <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                  <View style={{ backgroundColor: `${sec.color}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                    <AppText variant="muted" style={{ fontSize: 10, color: sec.color }}>{DATA_CONFIDENCE_LABELS[ed.data_confidence] ?? 'Não informado'}</AppText>
                  </View>
                  {ed.is_manual_override && (
                    <View style={{ backgroundColor: `${colors.accentNeon}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                      <AppText variant="muted" style={{ fontSize: 10, color: colors.accentNeon }}>Validado manualmente</AppText>
                    </View>
                  )}
                </View>
                {editingId === ed.id ? (
                  <View style={{ gap: 8 }}>
                    <TextInput
                      style={{ backgroundColor: colors.bgElevated, borderRadius: 8, padding: 8, color: colors.textPrimary, fontSize: 12 }}
                      value={editUrl}
                      onChangeText={setEditUrl}
                      placeholder="https://..."
                      placeholderTextColor={colors.textMuted}
                      autoCapitalize="none"
                    />
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <Button title="Salvar link" onPress={() => saveUrl(ed.id)} loading={saving} style={{ flex: 1 }} />
                      <Button title="Cancelar" variant="ghost" onPress={() => setEditingId(null)} style={{ flex: 1 }} />
                    </View>
                  </View>
                ) : (
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <Pressable
                      onPress={() => { setEditingId(ed.id); setEditUrl(ed.official_source_url || ''); }}
                      style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4, padding: 6, backgroundColor: colors.bgElevated, borderRadius: 8 }}>
                      <Ionicons name="link-outline" size={14} color={colors.textMuted} />
                      <AppText variant="muted" style={{ fontSize: 11 }} numberOfLines={1}>{ed.official_source_url || 'Sem link oficial'}</AppText>
                    </Pressable>
                    <Pressable onPress={() => markHighConfidence(ed.id)}
                      style={{ padding: 6, backgroundColor: `${colors.accentNeon}15`, borderRadius: 8 }}>
                      <Ionicons name="checkmark-circle-outline" size={16} color={colors.accentNeon} />
                    </Pressable>
                  </View>
                )}
              </View>
            ))}
          </View>
        );
      })}
    </ScrollView>
  );
}

// ─── Sources Tab ──────────────────────────────────────────────────────────────

interface DataSource {
  id: number;
  org_name: string;
  source_name: string;
  connector_key: string;
  source_type: string;
  priority: string;
  enabled: boolean;
  fetch_schedule_cron: string;
}

function SourcesTab() {
  const { colors } = useTheme();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<DataSource[]>('/api/admin-panel/sources/');
      setSources(res.data);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao carregar fontes', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  async function toggleSource(source: DataSource) {
    setToggling(source.id);
    try {
      const res = await api.patch<DataSource>(`/api/admin-panel/sources/${source.id}/`, { enabled: !source.enabled });
      setSources((prev) => prev.map((s) => (s.id === source.id ? res.data : s)));
      Toast.show({ type: 'success', text1: `${source.source_name} ${res.data.enabled ? 'ativada' : 'desativada'}.` });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao alterar fonte', text2: extractApiError(err) });
    } finally {
      setToggling(null);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <LoadingBlock />;
  if (!sources.length) return <EmptyState title="Nenhuma fonte configurada." />;

  const grouped = sources.reduce<Record<string, DataSource[]>>((acc, s) => {
    const k = s.org_name || 'Outros';
    if (!acc[k]) acc[k] = [];
    acc[k].push(s);
    return acc;
  }, {});

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100 }}>
      {Object.entries(grouped).map(([org, items]) => (
        <View key={org} style={{ marginBottom: 16 }}>
          <AppText variant="section" style={{ marginBottom: 8 }}>{org}</AppText>
          {items.map((s) => (
            <View key={s.id} style={{ backgroundColor: colors.bgCard, borderRadius: 14, padding: 12, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontWeight: '600', fontSize: 13 }}>{s.source_name}</AppText>
                <AppText variant="muted" style={{ fontSize: 10, marginTop: 2 }}>{s.connector_key} • {s.source_type} • {s.priority}</AppText>
                <AppText variant="muted" style={{ fontSize: 10 }}>{s.fetch_schedule_cron}</AppText>
              </View>
              <Pressable onPress={() => toggleSource(s)} disabled={toggling === s.id} style={{ padding: 6 }}>
                {toggling === s.id ? (
                  <ActivityIndicator size="small" color={colors.accentNeon} />
                ) : (
                  <Ionicons name={s.enabled ? 'toggle' : 'toggle-outline'} size={28} color={s.enabled ? colors.accentNeon : colors.textMuted} />
                )}
              </Pressable>
            </View>
          ))}
        </View>
      ))}
    </ScrollView>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, accent, warn, colors }: { label: string; value: number | string; accent?: boolean; warn?: boolean; colors: any }) {
  return (
    <View style={{ width: '47%', backgroundColor: colors.bgCard, borderRadius: 16, padding: 12 }}>
      <AppText variant="muted" style={{ fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>{label}</AppText>
      <AppText variant="body" style={{ fontSize: 20, fontWeight: '700', color: accent ? colors.accentNeon : warn ? '#f59e0b' : colors.textPrimary }}>{value}</AppText>
    </View>
  );
}
