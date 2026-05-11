import React, { useCallback, useState } from 'react';
import { Alert, ActivityIndicator, Pressable, View } from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { haptic } from '../../hooks/useHaptic';
import { TournamentCard } from '../../components/TournamentCard';
import { listChildren, listChildWatchlist, listProfiles, listWatchlist, watchlistSummary, removeWatchlist, updateWatch } from '../../services/data';
import { ParentChild, PlayerProfile, WatchlistItem } from '../../types';

interface ChildWatchlistGroup {
  childName: string;
  childId: number;
  items: WatchlistItem[];
}

const TODAY = new Date().toISOString().slice(0, 10);

function isPast(item: WatchlistItem): boolean {
  const ed = item.edition_detail;
  const endDate = ed.end_date || ed.start_date;
  if (!endDate) return false;
  return endDate < TODAY;
}

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
  const { user } = useAuth();
  const navigation = useNavigation<StackNav>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [conflicts, setConflicts] = useState<Set<number>>(new Set());
  const [removing, setRemoving] = useState<number | null>(null);
  const [marking, setMarking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPast, setShowPast] = useState(false);
  const [profileNames, setProfileNames] = useState<Record<number, string>>({});
  const [childGroups, setChildGroups] = useState<ChildWatchlistGroup[]>([]);

  async function fetchAll(): Promise<void> {
    if (user?.role === 'parent') {
      const [children, sm] = await Promise.all([
        listChildren().catch(() => [] as ParentChild[]),
        watchlistSummary(),
      ]);
      const childList = children as ParentChild[];
      const childWatchlists = await Promise.all(
        childList.map((link) => listChildWatchlist(link.child).catch(() => [] as WatchlistItem[])),
      );
      const groups: ChildWatchlistGroup[] = childList.map((link, i) => ({
        childName: link.child_detail.full_name || link.child_detail.email,
        childId: link.child,
        items: childWatchlists[i] as WatchlistItem[],
      }));
      const allItems = groups.flatMap((g) => g.items);
      setChildGroups(groups);
      setItems(allItems);
      setSummary(sm);
      setConflicts(detectConflicts(allItems));
      setProfileNames({});
    } else {
      const [wl, sm, profs] = await Promise.all([listWatchlist(), watchlistSummary(), listProfiles().catch(() => [] as PlayerProfile[])]);
      const list = wl as WatchlistItem[];
      setChildGroups([]);
      setItems(list);
      setSummary(sm);
      setConflicts(detectConflicts(list));
      setProfileNames(Object.fromEntries((profs as PlayerProfile[]).map((p) => [p.id, p.display_name])));
    }
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

  async function handleMarkInscrito(item: WatchlistItem) {
    haptic.light();
    setMarking(item.id);
    try {
      const updated = await updateWatch(item.id, { user_status: 'registered_declared' });
      setItems((prev) => prev.map((i) => i.id === item.id ? { ...i, ...updated } : i));
      setSummary((prev: any) => prev ? { ...prev, active_registrations: (prev.active_registrations ?? 0) + 1 } : prev);
      Toast.show({ type: 'success', text1: 'Marcado como inscrito!' });
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao marcar como inscrito.' });
    } finally {
      setMarking(null);
    }
  }

  const activeItems = items.filter((i) => !isPast(i));
  const pastItems   = items.filter((i) => isPast(i));

  function renderGrouped(itemsToRender: WatchlistItem[]) {
    if (user?.role !== 'parent' || childGroups.length === 0) {
      // Non-parent: render items directly (no grouping needed)
      return itemsToRender.map(renderItem);
    }
    const itemSet = new Set(itemsToRender.map((i) => i.id));
    return childGroups
      .map((group) => {
        const filtered = group.items.filter((i) => itemSet.has(i.id));
        if (filtered.length === 0) return null;
        return (
          <View key={group.childId}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6, marginTop: 4 }}>
              <Ionicons name="person-outline" size={14} color={colors.accentBlue} />
              <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700' }}>{group.childName}</AppText>
            </View>
            {filtered.map(renderItem)}
          </View>
        );
      })
      .filter(Boolean);
  }

  function renderItem(item: WatchlistItem) {
    const isInscrito = item.user_status === 'registered_declared';
    return (
      <View key={item.id}>
        {conflicts.has(item.id) && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: -4, paddingHorizontal: 4 }}>
            <Ionicons name="warning" size={12} color={colors.statusClosing} />
            <AppText variant="caption" style={{ color: colors.statusClosing, fontSize: 10 }}>Conflito de datas</AppText>
          </View>
        )}
        <View>
          <TournamentCard
            edition={item.edition_detail}
            onPress={() => navigation.navigate('TournamentDetail', { id: item.edition_detail.id, edition: item.edition_detail })}
          />
          {/* Action row — below card */}
          <View style={{
            flexDirection: 'row', alignItems: 'center', gap: 8,
            marginTop: -12, marginBottom: 4,
            paddingHorizontal: 14, paddingTop: 10, paddingBottom: 8,
            backgroundColor: colors.bgElevated,
            borderBottomLeftRadius: 14, borderBottomRightRadius: 14,
            borderWidth: 1, borderTopWidth: 0,
            borderColor: colors.borderSubtle,
          }}>
            {/* Inscrito button */}
            <Pressable
              onPress={() => !isInscrito && handleMarkInscrito(item)}
              disabled={marking === item.id}
              style={{
                flex: 1,
                flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                paddingVertical: 7,
                backgroundColor: isInscrito ? `${colors.statusOpen}18` : `${colors.accentNeon}18`,
                borderRadius: 10, borderWidth: 1,
                borderColor: isInscrito ? `${colors.statusOpen}44` : `${colors.accentNeon}44`,
              }}
              hitSlop={4}
            >
              {marking === item.id
                ? <ActivityIndicator size="small" color={colors.accentNeon} />
                : <Ionicons name={isInscrito ? 'checkmark-circle' : 'add-circle-outline'} size={16} color={isInscrito ? colors.statusOpen : colors.accentNeon} />
              }
              <AppText variant="caption" style={{ color: isInscrito ? colors.statusOpen : colors.accentNeon, fontWeight: '700', fontSize: 12 }}>
                Inscrito
              </AppText>
            </Pressable>
            {/* Remove button */}
            <Pressable
              onPress={() => handleRemove(item)}
              disabled={removing === item.id}
              style={{ width: 40, height: 36, backgroundColor: `${colors.danger}18`, borderRadius: 10, borderWidth: 1, borderColor: `${colors.danger}44`, alignItems: 'center', justifyContent: 'center' }}
              hitSlop={4}
            >
              <Ionicons name={removing === item.id ? 'hourglass-outline' : 'trash-outline'} size={17} color={colors.danger} />
            </Pressable>
          </View>
        </View>
      </View>
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
        <>
          {/* Upcoming / active */}
          {activeItems.length > 0 && (
            <>
              <SectionHeader title="Próximos" subtitle={`${activeItems.length} torneio${activeItems.length > 1 ? 's' : ''}`} />
              {renderGrouped(activeItems)}
            </>
          )}

          {/* Past tournaments */}
          {pastItems.length > 0 && (
            <>
              <Pressable
                onPress={() => setShowPast((v) => !v)}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10 }}
              >
                <SectionHeader title="Passados" subtitle={`${pastItems.length} torneio${pastItems.length > 1 ? 's' : ''}`} />
                <Ionicons name={showPast ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
              </Pressable>
              {showPast && renderGrouped(pastItems)}
            </>
          )}
        </>
      )}
    </Screen>
  );
}
