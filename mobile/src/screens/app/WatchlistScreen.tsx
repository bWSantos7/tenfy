import React, { useCallback, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { haptic } from '../../hooks/useHaptic';
import { TournamentCard } from '../../components/TournamentCard';
import { listWatchlist, watchlistSummary, removeWatchlist } from '../../services/data';
import { WatchlistItem } from '../../types';

function detectConflicts(items: WatchlistItem[]): Set<number> {
  const conflicting = new Set<number>();
  const active = items.filter((item) => {
    const s = item.edition_detail.dynamic_status || item.edition_detail.status;
    return item.edition_detail.start_date && !['finished', 'canceled'].includes(s);
  });
  for (let i = 0; i < active.length; i++) {
    for (let j = i + 1; j < active.length; j++) {
      const a = active[i].edition_detail;
      const b = active[j].edition_detail;
      const aStart = new Date(a.start_date!);
      const aEnd = a.end_date ? new Date(a.end_date) : aStart;
      const bStart = new Date(b.start_date!);
      const bEnd = b.end_date ? new Date(b.end_date) : bStart;
      if (aStart <= bEnd && bStart <= aEnd) {
        conflicting.add(active[i].id);
        conflicting.add(active[j].id);
      }
    }
  }
  return conflicting;
}

type Props = BottomTabScreenProps<MainTabParamList, 'Watchlist'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;

export function WatchlistScreen(_: Props) {
  const { colors } = useTheme();
  const navigation = useNavigation<StackNav>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [conflicts, setConflicts] = useState<Set<number>>(new Set());
  const [removing, setRemoving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchAll(): Promise<void> {
    const [wl, sm] = await Promise.all([listWatchlist(), watchlistSummary()]);
    const list = wl as WatchlistItem[];
    setItems(list);
    setSummary(sm);
    setConflicts(detectConflicts(list));
  }

  useFocusEffect(
    useCallback(() => {
      let active = true;
      (async () => {
        setLoading(true);
        setError(null);
        try {
          await fetchAll();
        } catch {
          if (active) setError('Não foi possível carregar sua agenda agora.');
        } finally {
          if (active) setLoading(false);
        }
      })();
      return () => { active = false; };
    }, []),
  );

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      await fetchAll();
    } catch {
      setError('Não foi possível atualizar sua agenda agora.');
    }
    setRefreshing(false);
  }

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      await fetchAll();
    } catch {
      setError('Não foi possível carregar sua agenda agora.');
    } finally {
      setLoading(false);
    }
  }

  function handleRemove(item: WatchlistItem) {
    haptic.warning();
    Alert.alert(
      'Remover da agenda',
      `Remover "${item.edition_detail.title || item.edition_detail.tournament_name || 'este torneio'}" da sua agenda?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover',
          style: 'destructive',
          onPress: async () => {
            setRemoving(item.id);
            try {
              await removeWatchlist(item.id);
              setItems((prev) => prev.filter((i) => i.id !== item.id));
              haptic.success();
              Toast.show({ type: 'success', text1: 'Removido da agenda.' });
            } catch {
              Toast.show({ type: 'error', text1: 'Erro ao remover da agenda.' });
            } finally {
              setRemoving(null);
            }
          },
        },
      ],
    );
  }

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <SectionHeader title="Agenda" subtitle="Seus torneios acompanhados" />

      {summary ? (
        <Card>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {[
              { icon: 'calendar', label: 'Total', value: summary.total, color: colors.accentNeon },
              { icon: 'time-outline', label: 'Próximos', value: summary.upcoming, color: colors.accentBlue },
              { icon: 'checkmark-done-outline', label: 'Passados', value: summary.past, color: colors.textMuted },
              { icon: 'ticket-outline', label: 'Inscrições', value: summary.active_registrations, color: colors.statusClosing },
            ].map((stat) => (
              <View
                key={stat.label}
                style={{ flex: 1, alignItems: 'center', gap: 4, backgroundColor: colors.bgBase, borderRadius: 14, paddingVertical: 12, borderWidth: 1, borderColor: colors.borderSubtle }}
              >
                <Ionicons name={stat.icon as any} size={18} color={stat.color} />
                <AppText variant="body" style={{ fontWeight: '700', fontSize: 18, color: stat.color }}>{stat.value ?? 0}</AppText>
                <AppText variant="caption" style={{ fontSize: 10, textAlign: 'center', color: colors.textMuted }}>{stat.label}</AppText>
              </View>
            ))}
          </View>
        </Card>
      ) : null}

      {/* Conflict warning */}
      {conflicts.size > 0 && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: `${colors.statusClosing}18`, borderRadius: 14, padding: 12, borderWidth: 1, borderColor: `${colors.statusClosing}44`, marginBottom: 4 }}>
          <Ionicons name="warning-outline" size={18} color={colors.statusClosing} />
          <AppText variant="caption" style={{ flex: 1, color: colors.statusClosing }}>
            {`${conflicts.size} torneio${conflicts.size > 1 ? 's' : ''} com datas sobrepostas na sua agenda.`}
          </AppText>
        </View>
      )}

      {loading ? (
        <LoadingBlock />
      ) : error && items.length === 0 ? (
        <EmptyState
          icon="cloud-offline-outline"
          title="Não foi possível carregar"
          subtitle={error}
          action={<Button title="Tentar novamente" variant="ghost" onPress={reload} />}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon="calendar-outline"
          title="Sua agenda está vazia"
          subtitle="Procure um torneio na lista e toque em adicionar à agenda para começar a acompanhar."
        />
      ) : (
        items.map((item) => (
          <View key={item.id}>
            {conflicts.has(item.id) && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: -4, paddingHorizontal: 4 }}>
                <Ionicons name="warning" size={12} color={colors.statusClosing} />
                <AppText variant="caption" style={{ color: colors.statusClosing, fontSize: 10 }}>Conflito de datas</AppText>
              </View>
            )}
            <View style={{ position: 'relative' }}>
              <TournamentCard
                edition={item.edition_detail}
                onPress={() => navigation.navigate('TournamentDetail', { id: item.edition_detail.id, edition: item.edition_detail })}
              />
              {/* Remove from agenda button */}
              <Pressable
                onPress={() => handleRemove(item)}
                disabled={removing === item.id}
                style={{ position: 'absolute', right: 10, bottom: 18, width: 44, height: 44, backgroundColor: `${colors.danger}26`, borderRadius: 12, borderWidth: 1, borderColor: `${colors.danger}4D`, alignItems: 'center', justifyContent: 'center' }}
                hitSlop={10}
              >
                <Ionicons name={removing === item.id ? 'hourglass-outline' : 'trash-outline'} size={18} color={colors.danger} />
              </Pressable>
            </View>
          </View>
        ))
      )}
    </Screen>
  );
}
