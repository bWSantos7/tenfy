import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  ListRenderItem,
  Pressable,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, EmptyState, Input, Screen } from '../../components/ui';
import { TournamentCard } from '../../components/TournamentCard';
import { TournamentListSkeleton } from '../../components/Skeleton';
import { Organization, TournamentEditionList } from '../../types';
import { calendar, listEditions, listFederations } from '../../services/tournaments';

type Props = BottomTabScreenProps<MainTabParamList, 'Tournaments'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;
type ViewMode = 'list' | 'calendar';

const MONTHS_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const WEEKDAYS_PT = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
const TODAY = new Date().toISOString().slice(0, 10);

const STATUS_FILTERS = [
  { key: '', label: 'Todos' },
  { key: 'open', label: 'Abertos' },
  { key: 'closing_soon', label: 'Fechando' },
  { key: 'announced', label: 'Anunciados' },
];

const CIRCUIT_FILTERS = [
  { key: 'CBT',   label: 'CBT' },
  { key: 'FPT',   label: 'FPT' },
  { key: 'COSAT', label: 'COSAT' },
  { key: 'ITF',   label: 'ITF' },
  { key: 'UTR',   label: 'UTR' },
];

export function TournamentsScreen({ route }: Props) {
  const { colors } = useTheme();
  const navigation = useNavigation<StackNav>();

  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [items, setItems] = useState<TournamentEditionList[]>([]);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [calendarMap, setCalendarMap] = useState<Record<string, TournamentEditionList[]>>({});
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [circuitFilter, setCircuitFilter] = useState('');
  const [federations, setFederations] = useState<Organization[]>([]);
  const [federationFilter, setFederationFilter] = useState<number | undefined>(route.params?.organization);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [calMonth, setCalMonth] = useState(() => new Date());
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<number[]>([]);

  async function loadList(q = query, status = statusFilter, circuit = circuitFilter, organization = federationFilter, category = categoryFilter, page = 1) {
    if (page === 1) setLoading(true);
    else setLoadingMore(true);
    try {
      const data = await listEditions({
        page,
        page_size: 20,
        q: q || undefined,
        status: status || undefined,
        circuit: circuit || undefined,
        organization,
        category: category || undefined,
      });
      const results = data.results || [];
      setItems((prev) => page === 1 ? results : [...prev, ...results]);
      setNextPage(data.next ? page + 1 : null);
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao carregar torneios' });
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }

  async function loadCalendar() {
    setLoading(true);
    try {
      const months = await calendar({
        status: statusFilter || undefined,
        circuit: circuitFilter || undefined,
        organization: federationFilter,
      });
      const map: Record<string, TournamentEditionList[]> = {};
      months.forEach((m) => {
        m.items.forEach((ed) => {
          if (ed.start_date) {
            const key = ed.start_date.slice(0, 10);
            if (!map[key]) map[key] = [];
            map[key].push(ed);
          }
        });
      });
      setCalendarMap(map);
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao carregar calendário' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (viewMode === 'list') loadList();
    else loadCalendar();
  }, [viewMode, federationFilter]);

  useEffect(() => {
    listFederations()
      .then(setFederations)
      .catch(() => setFederations([]));
  }, []);

  useEffect(() => {
    if (route.params?.circuit) {
      setCircuitFilter(route.params.circuit);
      loadList(query, statusFilter, route.params.circuit, federationFilter, categoryFilter);
    }
    if (route.params?.organization) {
      setFederationFilter(route.params.organization);
    }
  }, [route.params?.circuit, route.params?.organization]);

  function onQueryChange(v: string) {
    setQuery(v);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => loadList(v, statusFilter, circuitFilter, federationFilter, categoryFilter), 500);
  }

  function onStatusFilter(key: string) {
    const next = statusFilter === key ? '' : key;
    setStatusFilter(next);
    loadList(query, next, circuitFilter, federationFilter, categoryFilter);
  }

  function onCircuitFilter(key: string) {
    const next = circuitFilter === key ? '' : key;
    setCircuitFilter(next);
    loadList(query, statusFilter, next, federationFilter, categoryFilter);
  }

  function onFederationFilter(id: number | undefined) {
    const next = federationFilter === id ? undefined : id;
    setFederationFilter(next);
    loadList(query, statusFilter, circuitFilter, next, categoryFilter);
  }

  function onCategoryFilter(value: string) {
    setCategoryFilter(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(
      () => loadList(query, statusFilter, circuitFilter, federationFilter, value),
      500,
    );
  }

  function toggleCompareMode() { setCompareMode((v) => !v); setCompareIds([]); }

  function toggleCompareId(id: number) {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) { Toast.show({ type: 'info', text1: 'Máximo 3 torneios para comparar' }); return prev; }
      return [...prev, id];
    });
  }

  function startCompare() {
    if (compareIds.length < 2) { Toast.show({ type: 'info', text1: 'Selecione pelo menos 2 torneios' }); return; }
    navigation.navigate('TournamentCompare', { ids: compareIds });
    setCompareMode(false); setCompareIds([]);
  }

  function handleEndReached() {
    if (nextPage && !loadingMore && viewMode === 'list') {
      loadList(query, statusFilter, circuitFilter, federationFilter, categoryFilter, nextPage);
    }
  }

  // FlatList renderItem — memoized to prevent re-renders
  const renderItem: ListRenderItem<TournamentEditionList> = useCallback(({ item: ed }) => {
    const selected = compareIds.includes(ed.id);
    return (
      <View style={{ position: 'relative' }}>
        {compareMode && (
          <Pressable
            onPress={() => toggleCompareId(ed.id)}
            style={[styles.compareCheckbox, { borderColor: selected ? colors.accentBlue : colors.borderSubtle, backgroundColor: selected ? colors.accentBlue : colors.bgCard }]}
          >
            {selected && <Ionicons name="checkmark" size={14} color="#fff" />}
          </Pressable>
        )}
        <TournamentCard
          edition={ed}
          onPress={() => compareMode ? toggleCompareId(ed.id) : navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })}
        />
      </View>
    );
  }, [compareMode, compareIds, colors]);

  const keyExtractor = useCallback((item: TournamentEditionList) => String(item.id), []);

  // Header for FlatList (search + filter chips)
  const ListHeader = (
    <View>
      <Input value={query} onChangeText={onQueryChange} placeholder="Buscar por nome, cidade, circuito..." />
      <Input
        value={categoryFilter}
        onChangeText={onCategoryFilter}
        placeholder="Categoria (ex.: 16M, GA, Sub-12)"
      />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
        <View style={{ flexDirection: 'row', gap: 6, paddingRight: 8 }}>
          {STATUS_FILTERS.map((f) => {
            const active = statusFilter === f.key;
            return (
              <Pressable key={f.key} onPress={() => onStatusFilter(f.key)}
                style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: active ? colors.accentNeon : colors.bgCard, borderWidth: 1, borderColor: active ? colors.accentNeon : colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: active ? colors.bgBase : colors.textSecondary, fontWeight: '600' }}>{f.label}</AppText>
              </Pressable>
            );
          })}
          <View style={{ width: 1, backgroundColor: colors.borderSubtle, marginHorizontal: 2 }} />
          {CIRCUIT_FILTERS.map((f) => {
            const active = circuitFilter === f.key;
            return (
              <Pressable key={f.key} onPress={() => onCircuitFilter(f.key)}
                style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: active ? colors.accentBlue : colors.bgCard, borderWidth: 1, borderColor: active ? colors.accentBlue : colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: active ? '#fff' : colors.textSecondary, fontWeight: '600' }}>{f.label}</AppText>
              </Pressable>
            );
          })}
          {federations.length > 0 ? (
            <>
              <View style={{ width: 1, backgroundColor: colors.borderSubtle, marginHorizontal: 2 }} />
              {federations.map((f) => {
                const active = federationFilter === f.id;
                return (
                  <Pressable key={f.id} onPress={() => onFederationFilter(f.id)}
                    style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: active ? colors.accentNeon : colors.bgCard, borderWidth: 1, borderColor: active ? colors.accentNeon : colors.borderSubtle }}>
                    <AppText variant="caption" style={{ color: active ? colors.bgBase : colors.textSecondary, fontWeight: '600' }}>{f.short_name || f.name}</AppText>
                  </Pressable>
                );
              })}
            </>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );

  const year = calMonth.getFullYear();
  const month = calMonth.getMonth();
  const firstDayOfMonth = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  function dayKey(day: number) { return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`; }
  const selectedDayItems = selectedDate ? (calendarMap[selectedDate] ?? []) : [];

  return (
    <Screen scroll={false}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View>
          <AppText variant="title">Torneios</AppText>
          <AppText variant="caption" style={{ color: colors.textMuted }}>Torneios infantojuvenis agregados</AppText>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          {viewMode === 'list' && (
            <Pressable onPress={toggleCompareMode}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 9, backgroundColor: compareMode ? colors.accentBlue : colors.bgCard, borderWidth: 1, borderColor: compareMode ? colors.accentBlue : colors.borderSubtle }}>
              <Ionicons name="git-compare-outline" size={18} color={compareMode ? '#fff' : colors.textMuted} />
            </Pressable>
          )}
          <View style={{ flexDirection: 'row', backgroundColor: colors.bgCard, borderRadius: 12, padding: 3, borderWidth: 1, borderColor: colors.borderSubtle }}>
            <Pressable onPress={() => { setViewMode('list'); setSelectedDate(null); setCompareMode(false); setCompareIds([]); }}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 9, backgroundColor: viewMode === 'list' ? colors.accentNeon : 'transparent' }}>
              <Ionicons name="list" size={18} color={viewMode === 'list' ? colors.bgBase : colors.textMuted} />
            </Pressable>
            <Pressable onPress={() => setViewMode('calendar')}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 9, backgroundColor: viewMode === 'calendar' ? colors.accentNeon : 'transparent' }}>
              <Ionicons name="calendar" size={18} color={viewMode === 'calendar' ? colors.bgBase : colors.textMuted} />
            </Pressable>
          </View>
        </View>
      </View>

      {viewMode === 'list' ? (
        <>
          <FlatList
            data={loading ? [] : items}
            keyExtractor={keyExtractor}
            renderItem={renderItem}
            ListHeaderComponent={ListHeader}
            ListEmptyComponent={
              loading ? <TournamentListSkeleton count={6} /> : <EmptyState title="Nenhum torneio encontrado." subtitle="Tente ajustar a busca ou os filtros." />
            }
            ListFooterComponent={loadingMore ? <TournamentListSkeleton count={2} /> : null}
            onEndReached={handleEndReached}
            onEndReachedThreshold={0.4}
            contentContainerStyle={{ paddingBottom: 100 }}
            showsVerticalScrollIndicator={false}
            // Performance tuning for 3000 users / large lists
            windowSize={7}
            maxToRenderPerBatch={10}
            updateCellsBatchingPeriod={30}
            initialNumToRender={10}
            removeClippedSubviews
          />

          {compareMode && compareIds.length >= 2 && (
            <TouchableOpacity style={[styles.compareBtn, { backgroundColor: colors.accentBlue }]} onPress={startCompare} activeOpacity={0.85}>
              <Ionicons name="git-compare-outline" size={18} color="#fff" />
              <AppText variant="caption" style={{ color: '#fff', fontWeight: '700', marginLeft: 6 }}>Comparar ({compareIds.length})</AppText>
            </TouchableOpacity>
          )}
        </>
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 100 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <Pressable onPress={() => { setCalMonth(new Date(year, month - 1, 1)); setSelectedDate(null); }} style={{ padding: 8 }}>
              <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
            </Pressable>
            <AppText variant="body" style={{ fontWeight: '700', fontSize: 16 }}>{MONTHS_PT[month]} {year}</AppText>
            <Pressable onPress={() => { setCalMonth(new Date(year, month + 1, 1)); setSelectedDate(null); }} style={{ padding: 8 }}>
              <Ionicons name="chevron-forward" size={20} color={colors.textPrimary} />
            </Pressable>
          </View>

          <View style={{ flexDirection: 'row', marginBottom: 4 }}>
            {WEEKDAYS_PT.map((d, i) => (
              <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                <AppText variant="caption" style={{ color: colors.textMuted, fontWeight: '700', fontSize: 11 }}>{d}</AppText>
              </View>
            ))}
          </View>

          {loading ? <TournamentListSkeleton count={3} /> : (
            <>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: 8 }}>
                {Array.from({ length: firstDayOfMonth }).map((_, i) => <View key={`empty-${i}`} style={{ width: `${100 / 7}%` }} />)}
                {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => {
                  const key = dayKey(day);
                  const count = calendarMap[key]?.length ?? 0;
                  const hasItems = count > 0;
                  const isToday = key === TODAY;
                  const isSelected = key === selectedDate;
                  return (
                    <Pressable key={day} onPress={() => setSelectedDate(isSelected ? null : key)}
                      style={{ width: `${100 / 7}%`, alignItems: 'center', paddingVertical: 4 }}>
                      <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: isSelected ? colors.accentNeon : isToday ? `${colors.accentNeon}22` : 'transparent', borderWidth: isToday && !isSelected ? 1 : 0, borderColor: colors.accentNeon }}>
                        <AppText variant="caption" style={{ fontWeight: hasItems ? '700' : '400', color: isSelected ? colors.bgBase : isToday ? colors.accentNeon : hasItems ? colors.textPrimary : colors.textMuted }}>
                          {day}
                        </AppText>
                      </View>
                      <View style={{ flexDirection: 'row', gap: 2, marginTop: 2, height: 6, alignItems: 'center' }}>
                        {hasItems && !isSelected ? Array.from({ length: Math.min(count, 3) }).map((_, i) => (
                          <View key={i} style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: colors.accentNeon }} />
                        )) : null}
                      </View>
                    </Pressable>
                  );
                })}
              </View>

              {selectedDate ? (
                <View style={{ marginTop: 8 }}>
                  <AppText variant="body" style={{ fontWeight: '700', marginBottom: 8 }}>
                    {parseInt(selectedDate.slice(8), 10)} de {MONTHS_PT[parseInt(selectedDate.slice(5, 7), 10) - 1]}
                  </AppText>
                  {selectedDayItems.length === 0
                    ? <AppText variant="muted" style={{ textAlign: 'center', marginVertical: 16 }}>Nenhum torneio começa neste dia</AppText>
                    : selectedDayItems.map((ed) => <TournamentCard key={ed.id} edition={ed} onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })} />)
                  }
                </View>
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', marginTop: 8 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accentNeon }} />
                  <AppText variant="caption" style={{ color: colors.textMuted }}>Toque em um dia para ver os torneios</AppText>
                </View>
              )}
            </>
          )}
        </ScrollView>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  compareCheckbox: {
    position: 'absolute', top: 10, right: 10, zIndex: 10,
    width: 24, height: 24, borderRadius: 12, borderWidth: 2,
    alignItems: 'center', justifyContent: 'center',
  },
  compareBtn: {
    position: 'absolute', bottom: 20, alignSelf: 'center',
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 24, paddingVertical: 12,
    borderRadius: 30, elevation: 4,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.3, shadowRadius: 4,
  },
});
