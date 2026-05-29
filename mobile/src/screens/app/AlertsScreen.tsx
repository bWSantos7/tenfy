import React, { useCallback, useState } from 'react';
import { Pressable, Switch, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { Alert } from '../../types';
import { listAlerts, markAlertRead, markAllAlertsRead, respondDependentInvite } from '../../services/data';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen } from '../../components/ui';
import { haptic } from '../../hooks/useHaptic';
import api from '../../services/api';

type Props = BottomTabScreenProps<MainTabParamList, 'Alerts'>;
type PrefsTab = 'alerts' | 'prefs';

type ThemeColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

const FIELD_MAP: Record<string, string> = {
  entry_open_at:    'Inscrições abertas em',
  entry_close_at:   'Prazo de inscrição',
  start_date:       'Data de início',
  end_date:         'Data de encerramento',
  status:           'Status',
  venue:            'Local',
  venue_city:       'Cidade',
  venue_state:      'Estado',
  title:            'Título',
  base_price_brl:   'Valor da inscrição',
  surface:          'Superfície',
  modality:         'Modalidade',
  description:      'Descrição',
  new:              'Novo valor',
  old:              'Valor anterior',
  before:           'Antes',
  after:            'Depois',
};

const STATUS_LABELS_PT: Record<string, string> = {
  open:              'Aberto',
  closing_soon:      'Fechando em breve',
  closed:            'Encerrado',
  announced:         'Anunciado',
  draws_published:   'Chaves publicadas',
  in_progress:       'Em andamento',
  finished:          'Finalizado',
  canceled:          'Cancelado',
};

function fmtAlertDate(isoStr: string | null | undefined): string {
  if (!isoStr) return '';
  const date = new Date(isoStr);
  const now  = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1)    return 'agora mesmo';
  if (diffMin < 60)   return `há ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24)     return `há ${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7)      return `há ${diffD} dia${diffD > 1 ? 's' : ''}`;
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

function formatAlertValue(key: string, value: string): string {
  if (!value || value === 'None' || value === 'null') return '—';
  if (key === 'status') return STATUS_LABELS_PT[value] ?? value;
  if (key === 'base_price_brl') {
    const n = parseFloat(value.replace(',', '.'));
    if (!isNaN(n)) return `R$ ${n.toFixed(2).replace('.', ',')}`;
  }
  const isDatetimeKey = key.endsWith('_at');
  const isDateKey = key.endsWith('_date');
  const isChangeKey = key === 'old' || key === 'new' || key === 'before' || key === 'after';
  if (isDatetimeKey || isDateKey || isChangeKey) {
    try {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        // For _at fields or datetime strings (contain T+colon), show date + time
        if (isDatetimeKey || (isChangeKey && value.includes('T') && value.includes(':'))) {
          const dateStr = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
          const timeStr = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
          return `${dateStr} às ${timeStr}`;
        }
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
      }
    } catch { /* ignore */ }
  }
  return value;
}

function sanitizeAlertBody(body: string): string {
  if (!body) return '';
  const lines = body.split('\n');
  const parts: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const match = trimmed.match(/^([a-z_]+):\s*(.*)$/);
    if (match) {
      const [, key, raw] = match;
      const label = FIELD_MAP[key];
      if (label) {
        parts.push(`${label}: ${formatAlertValue(key, raw.trim())}`);
      }
      // silently drop unknown technical keys (e.g. 'entry', 'close', raw field names)
    } else {
      parts.push(trimmed);
    }
  }
  return parts.filter(Boolean).join('\n').trim();
}

function getKindConfig(c: ThemeColors): Record<string, { icon: string; color: string; label: string }> {
  return {
    deadline:  { icon: 'alarm-outline',         color: c.statusClosing, label: 'Prazo' },
    change:    { icon: 'create-outline',         color: c.accentBlue,    label: 'Alteração' },
    draws:     { icon: 'git-branch-outline',     color: c.statusProgress, label: 'Chaves' },
    canceled:  { icon: 'close-circle-outline',   color: c.danger,        label: 'Cancelado' },
    other:     { icon: 'notifications-outline',  color: c.statusClosed,  label: 'Outro' },
  };
}

interface AlertPrefs {
  in_app_enabled: boolean;
  push_enabled: boolean;
  changes_enabled: boolean;
  draws_enabled: boolean;
  deadline_days: number[];
}

export function AlertsScreen(_: Props) {
  const { colors } = useTheme();
  const [tab, setTab] = useState<PrefsTab>('alerts');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [prefs, setPrefs] = useState<AlertPrefs | null>(null);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [respondingInvite, setRespondingInvite] = useState<number | null>(null);

  useFocusEffect(
    useCallback(() => {
      loadAlerts();
      loadPrefs();
    }, []),
  );

  async function loadAlerts() {
    setLoading(true);
    setError(null);
    try {
      const data = await listAlerts();
      setAlerts(data as Alert[]);
    } catch {
      setError('Não foi possível carregar seus alertas agora.');
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const data = await listAlerts();
      setAlerts(data as Alert[]);
      await loadPrefs();
    } catch {
      setError('Não foi possível atualizar seus alertas agora.');
    } finally {
      setRefreshing(false);
    }
  }

  async function loadPrefs() {
    try {
      const res = await api.get<AlertPrefs>('/api/alerts/preferences/');
      setPrefs(res.data);
    } catch (err) {
      // Non-critical: prefs load failure should not block alert viewing.
      // Log for debugging without showing a disruptive error to the user.
      console.warn('[AlertsScreen] loadPrefs failed:', err);
    }
  }

  async function readOne(id: number) {
    haptic.select();
    try {
      await markAlertRead(id);
      setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, status: 'read', read_at: new Date().toISOString() } : a));
    } catch {
      Toast.show({ type: 'error', text1: 'Não foi possível marcar o alerta' });
    }
  }

  async function readAll() {
    haptic.success();
    try {
      await markAllAlertsRead();
      setAlerts((prev) => prev.map((a) => ({ ...a, status: 'read', read_at: new Date().toISOString() })));
      Toast.show({ type: 'success', text1: 'Todos os alertas marcados como lidos.' });
    } catch {
      Toast.show({ type: 'error', text1: 'Não foi possível concluir a ação' });
    }
  }

  async function handleInviteResponse(alert: Alert, action: 'accept' | 'decline') {
    const inviteId = alert.payload?.invite_id as number | undefined;
    if (!inviteId) return;
    haptic.select();
    setRespondingInvite(alert.id);
    try {
      await respondDependentInvite(inviteId, action);
      if (action === 'accept') {
        Toast.show({ type: 'success', text1: 'Convite aceito!', text2: 'Você agora é dependente do responsável.' });
      } else {
        Toast.show({ type: 'info', text1: 'Convite recusado.' });
      }
      // Remove the invite alert from the list since we responded
      setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Não foi possível processar a resposta.';
      Toast.show({ type: 'error', text1: 'Erro', text2: msg });
    } finally {
      setRespondingInvite(null);
    }
  }

  async function savePrefs(patch: Partial<AlertPrefs>) {
    if (!prefs) return;
    const updated = { ...prefs, ...patch };
    setPrefs(updated);
    setSavingPrefs(true);
    try {
      await api.put('/api/alerts/preferences/', updated);
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao salvar preferências' });
    } finally {
      setSavingPrefs(false);
    }
  }

  const unreadCount = alerts.filter((a) => a.status !== 'read').length;
  const KIND_CONFIG = getKindConfig(colors);

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <View>
          <AppText variant="title">Alertas</AppText>
          <AppText variant="caption" style={{ color: colors.textMuted }}>
            {unreadCount > 0 ? `${unreadCount} não lido${unreadCount > 1 ? 's' : ''}` : 'Tudo em dia'}
          </AppText>
        </View>
        <View style={{ flexDirection: 'row', backgroundColor: colors.bgCard, borderRadius: 12, padding: 3, borderWidth: 1, borderColor: colors.borderSubtle }}>
          <Pressable
            onPress={() => setTab('alerts')}
            style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 9, backgroundColor: tab === 'alerts' ? colors.accentNeon : 'transparent' }}
          >
            <AppText variant="caption" style={{ color: tab === 'alerts' ? colors.bgBase : colors.textMuted, fontWeight: '700' }}>
              Alertas{unreadCount > 0 ? ` (${unreadCount})` : ''}
            </AppText>
          </Pressable>
          <Pressable
            onPress={() => setTab('prefs')}
            style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 9, backgroundColor: tab === 'prefs' ? colors.accentNeon : 'transparent' }}
          >
            <AppText variant="caption" style={{ color: tab === 'prefs' ? colors.bgBase : colors.textMuted, fontWeight: '700' }}>Preferências</AppText>
          </Pressable>
        </View>
      </View>

      {tab === 'alerts' ? (
        <>
          {unreadCount > 0 && (
            <Button title="Marcar tudo como lido" variant="ghost" onPress={readAll} style={{ marginBottom: 8 }} />
          )}
          {loading ? <LoadingBlock /> : error && alerts.length === 0 ? (
            <EmptyState
              icon="cloud-offline-outline"
              title="Não foi possível carregar"
              subtitle={error}
              action={<Button title="Tentar novamente" variant="ghost" onPress={loadAlerts} />}
            />
          ) : alerts.length === 0 ? (
            <EmptyState
              icon="notifications-off-outline"
              title="Nenhum alerta por enquanto"
              subtitle="Adicione torneios à sua agenda para receber avisos sobre prazos, alterações e chaves."
            />
          ) : (
            alerts.map((alert) => {
              const cfg = KIND_CONFIG[alert.kind] ?? KIND_CONFIG['other'];
              const isUnread = alert.status !== 'read';
              const isInvite = alert.payload?.action === 'dependent_invite';
              const isRespondingThis = respondingInvite === alert.id;

              return (
                <Pressable
                  key={alert.id}
                  onPress={() => !isInvite && isUnread ? readOne(alert.id) : undefined}
                >
                  <View style={{
                    backgroundColor: isUnread ? `${cfg.color}08` : colors.bgCard,
                    borderRadius: 16,
                    padding: 12,
                    marginBottom: 8,
                    borderWidth: 1,
                    borderColor: isUnread ? `${cfg.color}30` : colors.borderSubtle,
                  }}>
                    <View style={{ flexDirection: 'row', gap: 10 }}>
                      <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${cfg.color}20`, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <Ionicons name={isInvite ? 'people-outline' : cfg.icon as any} size={18} color={cfg.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                          <AppText variant="body" style={{ fontWeight: isUnread ? '700' : '500', flex: 1, fontSize: 13 }}>{alert.title}</AppText>
                          {isUnread && (
                            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: cfg.color }} />
                          )}
                        </View>
                        {alert.body ? (
                          <AppText variant="caption" numberOfLines={3} style={{ marginBottom: 4 }}>
                            {isInvite ? alert.body : sanitizeAlertBody(alert.body)}
                          </AppText>
                        ) : null}
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <View style={{ backgroundColor: `${cfg.color}15`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                            <AppText variant="muted" style={{ fontSize: 10, color: cfg.color }}>
                              {isInvite ? 'Convite familiar' : cfg.label}
                            </AppText>
                          </View>
                          <AppText variant="muted" style={{ fontSize: 10 }}>{fmtAlertDate(alert.created_at)}</AppText>
                        </View>
                      </View>
                    </View>

                    {/* Invite accept/decline buttons */}
                    {isInvite ? (
                      <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                        <Pressable
                          onPress={() => handleInviteResponse(alert, 'decline')}
                          disabled={isRespondingThis}
                          style={{ flex: 1, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.danger, alignItems: 'center' }}
                        >
                          <AppText variant="caption" style={{ color: colors.danger, fontWeight: '700' }}>
                            {isRespondingThis ? '...' : 'Recusar'}
                          </AppText>
                        </Pressable>
                        <Pressable
                          onPress={() => handleInviteResponse(alert, 'accept')}
                          disabled={isRespondingThis}
                          style={{ flex: 1, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.accentBlue, alignItems: 'center' }}
                        >
                          <AppText variant="caption" style={{ color: '#fff', fontWeight: '700' }}>
                            {isRespondingThis ? '...' : 'Aceitar'}
                          </AppText>
                        </Pressable>
                      </View>
                    ) : null}
                  </View>
                </Pressable>
              );
            })
          )}
        </>
      ) : (
        <PrefsPanel prefs={prefs} onSave={savePrefs} saving={savingPrefs} />
      )}
    </Screen>
  );
}

function PrefsPanel({ prefs, onSave, saving }: { prefs: AlertPrefs | null; onSave: (p: Partial<AlertPrefs>) => void; saving: boolean }) {
  const { colors } = useTheme();

  if (!prefs) return <LoadingBlock />;

  const rows: { label: string; sub: string; key: keyof AlertPrefs }[] = [
    { label: 'In-app', sub: 'Notificações dentro do app', key: 'in_app_enabled' },
    { label: 'Push', sub: 'Notificações push no dispositivo', key: 'push_enabled' },
    { label: 'Alterações', sub: 'Quando dados do torneio mudarem', key: 'changes_enabled' },
    { label: 'Chaves', sub: 'Quando as chaves forem publicadas', key: 'draws_enabled' },
  ];

  return (
    <Card>
      <AppText variant="body" style={{ fontWeight: '700', marginBottom: 12 }}>Preferências de notificação</AppText>
      {rows.map((row, i) => (
        <View key={row.key} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: i < rows.length - 1 ? 1 : 0, borderBottomColor: colors.borderSubtle }}>
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontSize: 14 }}>{row.label}</AppText>
            <AppText variant="muted" style={{ fontSize: 11 }}>{row.sub}</AppText>
          </View>
          <Switch
            value={prefs[row.key] as boolean}
            onValueChange={(v) => onSave({ [row.key]: v })}
            trackColor={{ false: colors.borderSubtle, true: `${colors.accentNeon}88` }}
            thumbColor={prefs[row.key] ? colors.accentNeon : colors.textMuted}
            disabled={saving}
          />
        </View>
      ))}
      <AppText variant="muted" style={{ marginTop: 12, fontSize: 11 }}>
        Prazo de aviso (dias antes): {(prefs.deadline_days || [7, 2, 0]).join(', ')} dias
      </AppText>
    </Card>
  );
}
