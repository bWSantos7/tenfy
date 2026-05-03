import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { AppText, EmptyState, Input, Screen, SelectField } from '../../components/ui';
import { TournamentCard } from '../../components/TournamentCard';
import { TournamentListSkeleton } from '../../components/Skeleton';
import { Organization, PlayerProfile, TournamentEditionList } from '../../types';
import { calendar, listEditions, listFederations, TournamentFilters } from '../../services/tournaments';
import { listProfiles } from '../../services/data';
import { pickBestProfile } from '../../utils/profile';

type Props = BottomTabScreenProps<MainTabParamList, 'Tournaments'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;
type ViewMode = 'list' | 'calendar';

const MONTHS_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const WEEKDAYS_PT = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
const TODAY = new Date().toISOString().slice(0, 10);
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function formatIsoDateInput(value: string) {
  const digits = value.replace(/\D/g, '').slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

function isValidIsoDate(value: string) {
  if (!ISO_DATE_RE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day;
}

const STATUS_FILTERS = [
  { key: '', label: 'Todos' },
  { key: 'open', label: 'Abertos' },
  { key: 'closing_soon', label: 'Fechando' },
  { key: 'announced', label: 'Anunciados' },
  { key: 'closed', label: 'Encerrados' },
  { key: 'in_progress', label: 'Em andamento' },
  { key: 'draws_published', label: 'Chaves' },
  { key: 'finished', label: 'Finalizados' },
  { key: 'canceled', label: 'Cancelados' },
];

const CIRCUIT_FILTERS = [
  { key: 'CBT',   label: 'CBT' },
  { key: 'FPT',   label: 'FPT' },
  { key: 'COSAT', label: 'COSAT' },
  { key: 'ITF',   label: 'ITF' },
  { key: 'UTR',   label: 'UTR' },
];

const STATE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todas' },
  ...['SP','RJ','MG','RS','SC','PR','BA','PE','CE','DF','GO','ES','MT','MS','PA','AM','MA','RN','PB','AL','SE','PI','TO','RO','RR','AP','AC']
    .map((uf) => ({ value: uf, label: uf })),
];

const MODALITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todas' },
  { value: 'tennis', label: 'Tênis' },
  { value: 'beach_tennis', label: 'Beach Tennis' },
  { value: 'padel', label: 'Padel' },
  { value: 'wheelchair', label: 'Cadeira de rodas' },
];

const SURFACE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todas' },
  { value: 'clay', label: 'Saibro' },
  { value: 'hard', label: 'Rápida / Sintética' },
  { value: 'grass', label: 'Grama' },
  { value: 'sand', label: 'Areia' },
  { value: 'carpet', label: 'Carpete' },
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

  // Filters
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [circuitFilter, setCircuitFilter] = useState('');
  const [federations, setFederations] = useState<Organization[]>([]);
  const [federationFilter, setFederationFilter] = useState<number | undefined>(route.params?.organization);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [cityFilter, setCityFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [modalityFilter, setModalityFilter] = useState('');
  const [surfaceFilter, setSurfaceFilter] = useState('');
  const [nearMe, setNearMe] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Calendar UI state
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [calMonth, setCalMonth] = useState(() => new Date());

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reloadVersion = useRef(0);

  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<number[]>([]);

  function buildFilters(): TournamentFilters {
    const f: TournamentFilters = {};
    if (query) f.q = query;
    if (statusFilter) f.status = statusFilter;
    if (circuitFilter) f.circuit = circuitFilter;
    if (federationFilter) f.organization = federationFilter;
    if (categoryFilter) f.category = categoryFilter;
    if (stateFilter) f.state = stateFilter;
    if (cityFilter) f.city = cityFilter;
    if (fromDate && isValidIsoDate(fromDate)) f.from_date = fromDate;
    if (toDate && isValidIsoDate(toDate)) f.to_date = toDate;
    if (modalityFilter) f.modality = modalityFilter;
    if (surfaceFilter) f.surface = surfaceFilter;
    if (nearMe && primaryProfileId) f.near_profile = primaryProfileId;
    return f;
  }

  const activeAdvancedCount = useMemo(() => {
    let n = 0;
    if (stateFilter) n++;
    if (cityFilter) n++;
    if (fromDate) n++;
    if (toDate) n++;
    if (modalityFilter) n++;
    if (surfaceFilter) n++;
    if (nearMe) n++;
    return n;
  }, [stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter, nearMe]);

  const hasAnyFilter = useMemo(() => !!(
    query || statusFilter || circuitFilter || federationFilter || categoryFilter || activeAdvancedCount > 0
  ), [query, statusFilter, circuitFilter, federationFilter, categoryFilter, activeAdvancedCount]);

  async function loadList(page = 1) {
    const myVersion = ++reloadVersion.current;
    if (page === 1) {
      setLoading(true);
      setNextPage(null);
    } else {
      setLoadingMore(true);
    }
    try {
      const data = await listEditions({
        ...buildFilters(),
        page,
        page_size: 20,
      });
      if (myVersion !== reloadVersion.current) return;
      const results = data.results || [];
      setItems((prev) => page === 1 ? results : [...prev, ...results]);
      setNextPage(data.next ? page + 1 : null);
    } catch {
      if (myVersion === reloadVersion.current) {
        Toast.show({ type: 'error', text1: 'Erro ao carregar torneios' });
      }
    } finally {
      if (myVersion === reloadVersion.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }

  async function loadCalendar() {
    const myVersion = ++reloadVersion.current;
    setLoading(true);
    try {
      const months = await calendar(buildFilters());
      if (myVersion !== reloadVersion.current) return;
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
      if (myVersion === reloadVersion.current) {
        Toast.show({ type: 'error', text1: 'Erro ao carregar calendário' });
      }
    } finally {
      if (myVersion === reloadVersion.current) setLoading(false);
    }
  }

  // Load primary profile (for "Perto de mim" filter)
  useEffect(() => {
    listProfiles()
      .then((profiles) => {
        const primary = pickBestProfile(profiles as PlayerProfile[]);
        if (primary) setPrimaryProfileId(primary.id);
      })
      .catch(() => {});
  }, []);

  // Load federations once
  useEffect(() => {
    listFederations()
      .then(setFederations)
      .catch(() => setFederations([]));
  }, []);

  // Reload list/calendar whenever any filter or view mode changes (debounced for free-text fields)
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    const isTextFilter = !!(query || categoryFilter || cityFilter || fromDate || toDate);
    const delay = isTextFilter ? 400 : 0;
    debounceTimer.current = setTimeout(() => {
      if (viewMode === 'list') loadList(1);
      else loadCalendar();
    }, delay);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    viewMode, query, statusFilter, circuitFilter, federationFilter, categoryFilter,
    stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
    nearMe, primaryProfileId,
  ]);

  // Apply incoming route params (deep-link / cross-screen navigation)
  useEffect(() => {
    if (route.params?.circuit) setCircuitFilter(route.params.circuit);
    if (route.params?.organization) setFederationFilter(route.params.organization);
  }, [route.params?.circuit, route.params?.organization]);

  function onStatusFilter(key: string) {
    setStatusFilter((prev) => prev === key ? '' : key);
  }

  function onCircuitFilter(key: string) {
    setCircuitFilter((prev) => prev === key ? '' : key);
  }

  function onFederationFilter(id: number | undefined) {
    setFederationFilter((prev) => prev === id ? undefined : id);
  }

  function clearFilters() {
    setQuery('');
    setStatusFilter('');
    setCircuitFilter('');
    setFederationFilter(undefined);
    setCategoryFilter('');
    setStateFilter('');
    setCityFilter('');
    setFromDate('');
    setToDate('');
    setModalityFilter('');
    setSurfaceFilter('');
    setNearMe(false);
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
    if (nextPage && !loading && !loadingMore && viewMode === 'list') {
      loadList(nextPage);
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

  // Header for FlatList (search + filter chips + advanced panel)
  const ListHeader = (
    <View>
      <Input value={query} onChangeText={setQuery} placeholder="Buscar por nome, cidade, circuito..." />
      <Input
        value={categoryFilter}
        onChangeText={setCategoryFilter}
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

      {/* Advanced filters toggle row */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Pressable
          onPress={() => setShowAdvanced((v) => !v)}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6,
            paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
            backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.borderSubtle,
          }}
        >
          <Ionicons name="options-outline" size={16} color={colors.textSecondary} />
          <AppText variant="caption" style={{ fontWeight: '600' }}>
            {showAdvanced ? 'Ocultar filtros' : 'Mais filtros'}
          </AppText>
          {activeAdvancedCount > 0 ? (
            <View style={{ minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 5, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center' }}>
              <AppText variant="caption" style={{ color: colors.bgBase, fontWeight: '700', fontSize: 11 }}>{activeAdvancedCount}</AppText>
            </View>
          ) : null}
        </Pressable>
        {primaryProfileId ? (
          <Pressable
            onPress={() => setNearMe((v) => !v)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
              backgroundColor: nearMe ? colors.accentNeon : colors.bgCard,
              borderWidth: 1, borderColor: nearMe ? colors.accentNeon : colors.borderSubtle,
            }}
          >
            <Ionicons name="location-outline" size={16} color={nearMe ? colors.bgBase : colors.textSecondary} />
            <AppText variant="caption" style={{ color: nearMe ? colors.bgBase : colors.textSecondary, fontWeight: '600' }}>
              Perto de mim
            </AppText>
          </Pressable>
        ) : null}
        {hasAnyFilter ? (
          <Pressable onPress={clearFilters} style={{ marginLeft: 'auto', paddingHorizontal: 8, paddingVertical: 8 }}>
            <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>Limpar</AppText>
          </Pressable>
        ) : null}
      </View>

      {showAdvanced ? (
        <View style={{ gap: 10, padding: 12, marginBottom: 10, borderRadius: 12, backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.borderSubtle }}>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <SelectField
                label="UF"
                value={stateFilter}
                options={STATE_OPTIONS}
                onSelect={setStateFilter}
                placeholder="Todas"
                searchable
              />
            </View>
            <View style={{ flex: 1.4 }}>
              <Input
                label="Cidade"
                value={cityFilter}
                onChangeText={setCityFilter}
                placeholder="Ex.: São Paulo"
                autoCapitalize="words"
              />
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Input
                label="Data inicial"
                value={fromDate}
                onChangeText={(value) => setFromDate(formatIsoDateInput(value))}
                placeholder="AAAA-MM-DD"
                keyboardType="numbers-and-punctuation"
                autoCapitalize="none"
                autoCorrect={false}
                maxLength={10}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Input
                label="Data final"
                value={toDate}
                onChangeText={(value) => setToDate(formatIsoDateInput(value))}
                placeholder="AAAA-MM-DD"
                keyboardType="numbers-and-punctuation"
                autoCapitalize="none"
                autoCorrect={false}
                maxLength={10}
              />
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <SelectField
                label="Modalidade"
                value={modalityFilter}
                options={MODALITY_OPTIONS}
                onSelect={setModalityFilter}
                placeholder="Todas"
              />
            </View>
            <View style={{ flex: 1 }}>
              <SelectField
                label="Superfície"
                value={surfaceFilter}
                options={SURFACE_OPTIONS}
                onSelect={setSurfaceFilter}
                placeholder="Todas"
              />
            </View>
          </View>
        </View>
      ) : null}
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
              loading
                ? <TournamentListSkeleton count={6} />
                : (
                  <EmptyState
                    title="Nenhum torneio encontrado."
                    subtitle={nearMe
                      ? 'Confira a cidade, UF e raio de viagem no seu perfil ou ajuste os filtros.'
                      : 'Tente ajustar a busca ou os filtros.'}
                  />
                )
            }
            ListFooterComponent={loadingMore ? <TournamentListSkeleton count={2} /> : null}
            onEndReached={handleEndReached}
            onEndReachedThreshold={0.4}
            contentContainerStyle={{ paddingBottom: 100 }}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
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
          {ListHeader}

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
