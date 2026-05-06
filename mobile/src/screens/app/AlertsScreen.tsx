import React, { useCallback, useState } from 'react';
import { Pressable, Switch, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { Alert } from '../../types';
import { listAlerts, markAlertRead, markAllAlertsRead } from '../../services/data';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen } from '../../components/ui';
import { haptic } from '../../hooks/useHaptic';
import { fmtDateTime } from '../../utils/format';
import api from '../../services/api';

type Props = BottomTabScreenProps<MainTabParamList, 'Alerts'>;
type PrefsTab = 'alerts' | 'prefs';

type ThemeColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

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
              return (
                <Pressable
                  key={alert.id}
                  onPress={() => isUnread ? readOne(alert.id) : undefined}
                >
                  <View style={{
                    backgroundColor: isUnread ? `${cfg.color}08` : colors.bgCard,
                    borderRadius: 16,
                    padding: 12,
                    marginBottom: 8,
                    flexDirection: 'row',
                    gap: 10,
                    borderWidth: 1,
                    borderColor: isUnread ? `${cfg.color}30` : colors.borderSubtle,
                  }}>
                    <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: `${cfg.color}20`, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Ionicons name={cfg.icon as any} size={18} color={cfg.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <AppText variant="body" style={{ fontWeight: isUnread ? '700' : '500', flex: 1, fontSize: 13 }}>{alert.title}</AppText>
                        {isUnread && (
                          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: cfg.color }} />
                        )}
                      </View>
                      {alert.body ? (
                        <AppText variant="caption" numberOfLines={2} style={{ marginBottom: 4 }}>{alert.body}</AppText>
                      ) : null}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <View style={{ backgroundColor: `${cfg.color}15`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                          <AppText variant="muted" style={{ fontSize: 10, color: cfg.color }}>{cfg.label}</AppText>
                        </View>
                        <AppText variant="muted" style={{ fontSize: 10 }}>{fmtDateTime(alert.created_at)}</AppText>
                      </View>
                    </View>
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
