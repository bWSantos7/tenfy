import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  FlatList,
  ListRenderItem,
  Pressable,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';
import { BottomTabBarHeightContext } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, EmptyState, Input, Screen, SelectField } from '../../components/ui';
import { TournamentCard } from '../../components/TournamentCard';
import { TournamentListSkeleton } from '../../components/Skeleton';
import { Organization, PlayerProfile, TournamentEditionList } from '../../types';
import { calendar, listEditions, listFederations, listCountries, TournamentFilters } from '../../services/tournaments';
import { listProfiles } from '../../services/data';
import { pickBestProfile } from '../../utils/profile';
import { resolveCountry } from '../../utils/country';
import { getActiveProfileId } from '../../utils/activeProfile';

type Props = BottomTabScreenProps<MainTabParamList, 'Tournaments'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;
type ViewMode = 'list' | 'calendar';

// ─── FilterHeader ─────────────────────────────────────────────────────────────
// MUST live outside TournamentsScreen so FlatList/ScrollView receive a stable
// component reference. Defining it inside causes FlatList to remount the header
// on every render (new function ref = new component type), which destroys TextInput
// focus and closes SelectField modals — breaking category and federation filters.

interface FilterHeaderProps {
  query: string;
  onQueryChange: (v: string) => void;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  activeFilterCount: number;
  hasAnyInput: boolean;
  onClearFilters: () => void;
  statusFilter: string;
  onStatusChange: (v: string) => void;
  federationFilter: number | undefined;
  onFederationChange: (v: string) => void;
  organizationOptions: { value: string; label: string }[];
  countryFilter: string;
  onCountryChange: (v: string) => void;
  countryOptions: { value: string; label: string }[];
  categoryFilter: string;
  onCategoryChange: (v: string) => void;
  stateFilter: string;
  onStateChange: (v: string) => void;
  cityFilter: string;
  onCityChange: (v: string) => void;
  fromDate: string;
  onFromDateChange: (v: string) => void;
  toDate: string;
  onToDateChange: (v: string) => void;
  modalityFilter: string;
  onModalityChange: (v: string) => void;
  surfaceFilter: string;
  onSurfaceChange: (v: string) => void;
  nearMe: boolean;
  onNearMeToggle: () => void;
  primaryProfileId: number | null;
  primaryProfile: PlayerProfile | null;
  totalCount: number | null;
  loading: boolean;
}

function FilterHeader({
  query, onQueryChange,
  showAdvanced, onToggleAdvanced,
  activeFilterCount, hasAnyInput, onClearFilters,
  statusFilter, onStatusChange,
  federationFilter, onFederationChange,
  organizationOptions,
  countryFilter, onCountryChange, countryOptions,
  categoryFilter, onCategoryChange,
  stateFilter, onStateChange,
  cityFilter, onCityChange,
  fromDate, onFromDateChange,
  toDate, onToDateChange,
  modalityFilter, onModalityChange,
  surfaceFilter, onSurfaceChange,
  nearMe, onNearMeToggle,
  primaryProfileId,
  primaryProfile,
  totalCount,
  loading,
}: FilterHeaderProps) {
  const { colors } = useTheme();
  return (
    <View>
      <Input value={query} onChangeText={onQueryChange} placeholder="Buscar por nome, cidade, circuito..." />

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, marginBottom: 8 }}>
        <Pressable
          onPress={onToggleAdvanced}
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
          {activeFilterCount > 0 ? (
            <View style={{ minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 5, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center' }}>
              <AppText variant="caption" style={{ color: colors.bgBase, fontWeight: '700', fontSize: 11 }}>{activeFilterCount}</AppText>
            </View>
          ) : null}
        </Pressable>
        {hasAnyInput ? (
          <Pressable onPress={onClearFilters} style={{ marginLeft: 'auto', paddingHorizontal: 8, paddingVertical: 8 }}>
            <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>Limpar</AppText>
          </Pressable>
        ) : null}
      </View>

      {!loading && totalCount !== null ? (
        <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 8 }}>
          {totalCount === 0
            ? 'Nenhum torneio encontrado'
            : totalCount === 1
              ? '1 torneio encontrado'
              : `${totalCount} torneios encontrados`}
        </AppText>
      ) : null}

      {showAdvanced ? (
        <View style={{ gap: 10, padding: 12, marginBottom: 10, borderRadius: 12, backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.borderSubtle }}>
          <SelectField label="Status" value={statusFilter} options={STATUS_FILTERS} onSelect={onStatusChange} placeholder="Todos" />

          <SelectField
            label="Organização / Federação"
            value={federationFilter ? String(federationFilter) : ''}
            options={organizationOptions}
            onSelect={onFederationChange}
            placeholder="Todas"
          />

          {countryOptions.length > 0 ? (
            <SelectField
              label="País"
              value={countryFilter}
              options={countryOptions}
              onSelect={onCountryChange}
              placeholder="Todos"
              searchable
            />
          ) : null}

          <SelectField
            label="Categoria (por idade)"
            value={categoryFilter}
            options={AGE_CATEGORY_OPTIONS}
            onSelect={onCategoryChange}
            placeholder="Todas as idades"
          />

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <SelectField label="UF" value={stateFilter} options={STATE_OPTIONS} onSelect={onStateChange} placeholder="Todas" searchable />
            </View>
            <View style={{ flex: 1.4 }}>
              <SelectField label="Cidade" value={cityFilter} options={CITY_OPTIONS} onSelect={onCityChange} placeholder="Todas" searchable />
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Input
                label="Data inicial" value={fromDate} onChangeText={onFromDateChange}
                placeholder="AAAA-MM-DD" keyboardType="numbers-and-punctuation"
                autoCapitalize="none" autoCorrect={false} maxLength={10}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Input
                label="Data final" value={toDate} onChangeText={onToDateChange}
                placeholder="AAAA-MM-DD" keyboardType="numbers-and-punctuation"
                autoCapitalize="none" autoCorrect={false} maxLength={10}
              />
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <SelectField label="Modalidade" value={modalityFilter} options={MODALITY_OPTIONS} onSelect={onModalityChange} placeholder="Todas" />
            </View>
            <View style={{ flex: 1 }}>
              <SelectField label="Superfície" value={surfaceFilter} options={SURFACE_OPTIONS} onSelect={onSurfaceChange} placeholder="Todas" />
            </View>
          </View>

          {primaryProfileId ? (
            <View>
              <Pressable
                onPress={onNearMeToggle}
                style={{
                  flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  paddingHorizontal: 14, paddingVertical: 12, borderRadius: 12,
                  backgroundColor: nearMe ? `${colors.accentNeon}22` : colors.bgBase,
                  borderWidth: 1, borderColor: nearMe ? colors.accentNeon : colors.borderSubtle,
                }}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                  <Ionicons name="location-outline" size={16} color={nearMe ? colors.accentNeon : colors.textSecondary} />
                  <View style={{ flex: 1 }}>
                    <AppText variant="caption" style={{ color: nearMe ? colors.accentNeon : colors.textSecondary, fontWeight: '600' }}>
                      Perto de mim
                    </AppText>
                    {primaryProfile?.home_city ? (
                      <AppText variant="muted" style={{ fontSize: 10, marginTop: 1 }}>
                        {primaryProfile.home_city}{primaryProfile.home_state ? `/${primaryProfile.home_state}` : ''}
                        {primaryProfile.federation_detail
                          ? ` • ${primaryProfile.federation_detail.short_name || primaryProfile.federation_detail.name}`
                          : (primaryProfile.travel_states && primaryProfile.travel_states.length > 0
                            ? ` • ${primaryProfile.travel_states.length >= 27 ? 'Todo o Brasil' : `${primaryProfile.travel_states.length} estado${primaryProfile.travel_states.length > 1 ? 's' : ''}`}`
                            : '')}
                      </AppText>
                    ) : (
                      <AppText variant="muted" style={{ fontSize: 10, marginTop: 1, color: colors.statusClosing }}>
                        Configure sua cidade no perfil para usar este filtro
                      </AppText>
                    )}
                  </View>
                </View>
                <Ionicons name={nearMe ? 'toggle' : 'toggle-outline'} size={28} color={nearMe ? colors.accentNeon : colors.textMuted} />
              </Pressable>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const MONTHS_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

const STATUS_SORT_PRIORITY: Record<string, number> = {
  open: 0,
  closing_soon: 0,
  announced: 1,
  in_progress: 1,
  draws_published: 1,
  closed: 2,
  finished: 3,
  canceled: 4,
  unknown: 5,
};

function sortTournaments(list: TournamentEditionList[]): TournamentEditionList[] {
  return [...list].sort((a, b) => {
    const pa = STATUS_SORT_PRIORITY[a.status ?? 'unknown'] ?? 5;
    const pb = STATUS_SORT_PRIORITY[b.status ?? 'unknown'] ?? 5;
    if (pa !== pb) return pa - pb;
    return (a.start_date || '').localeCompare(b.start_date || '');
  });
}
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
  { value: '', label: 'Todos' },
  { value: 'open', label: 'Abertos' },
  { value: 'closing_soon', label: 'Fechando' },
  { value: 'announced', label: 'Anunciados' },
  { value: 'closed', label: 'Encerrados' },
  { value: 'in_progress', label: 'Em andamento' },
  { value: 'draws_published', label: 'Chaves' },
  { value: 'finished', label: 'Finalizados' },
  { value: 'canceled', label: 'Cancelados' },
];

const AGE_CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todas as idades' },
  { value: '10', label: '10 anos' },
  { value: '12', label: '12 anos' },
  { value: '14', label: '14 anos' },
  { value: '16', label: '16 anos' },
  { value: '18', label: '18 anos' },
  { value: 'junior', label: 'Juvenil' },
  { value: 'adulto', label: 'Adulto' },
  { value: '40', label: 'Masters 40+' },
  { value: '50', label: 'Masters 50+' },
];

const CITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Todas as cidades' },
  ...([
    // SP
    'São Paulo','Campinas','Santos','Guarulhos','São Bernardo do Campo','Santo André',
    'Osasco','Ribeirão Preto','São José dos Campos','Sorocaba','Mogi das Cruzes',
    'Diadema','Jundiaí','Piracicaba','Bauru','São José do Rio Preto',
    'Franca','Presidente Prudente','Marília','Limeira','Taubaté',
    'Araraquara','Indaiatuba','Americana','Santa Bárbara d\'Oeste',
    // RJ
    'Rio de Janeiro','Niterói','Duque de Caxias','Nova Iguaçu','São Gonçalo',
    'Belford Roxo','Campos dos Goytacazes','Petrópolis','Volta Redonda','Macaé',
    // MG
    'Belo Horizonte','Uberlândia','Contagem','Juiz de Fora','Montes Claros',
    'Betim','Ribeirão das Neves','Uberaba','Governador Valadares','Ipatinga',
    'Sete Lagoas','Poços de Caldas','Divinópolis','Muriaé','Varginha',
    // RS
    'Porto Alegre','Caxias do Sul','Canoas','Pelotas','Santa Maria',
    'Gravataí','Novo Hamburgo','São Leopoldo','Rio Grande','Passo Fundo',
    'Viamão','Alvorada','Uruguaiana','Cachoeirinha',
    // SC
    'Florianópolis','Joinville','Blumenau','São José','Criciúma',
    'Chapecó','Itajaí','Jaraguá do Sul','Palhoça','Balneário Camboriú',
    // PR
    'Curitiba','Londrina','Maringá','Ponta Grossa','Cascavel',
    'São José dos Pinhais','Foz do Iguaçu','Colombo','Guarapuava','Paranaguá',
    // BA
    'Salvador','Feira de Santana','Vitória da Conquista','Camaçari','Itabuna',
    'Ilhéus','Lauro de Freitas','Juazeiro','Teixeira de Freitas',
    // PE
    'Recife','Olinda','Caruaru','Petrolina','Jaboatão dos Guararapes',
    'Paulista','Cabo de Santo Agostinho','Camaragibe',
    // CE
    'Fortaleza','Caucaia','Juazeiro do Norte','Maracanaú','Sobral',
    'Crato','Itapipoca','Maranguape',
    // DF / GO
    'Brasília','Goiânia','Aparecida de Goiânia','Anápolis','Rio Verde',
    'Águas Lindas de Goiás',
    // AM / PA
    'Manaus','Belém','Ananindeua','Santarém','Castanhal','Marabá',
    // RN / PB / AL / SE / MA / PI
    'Natal','João Pessoa','Campina Grande','Maceió','Aracaju',
    'São Luís','Imperatriz','Teresina',
    // ES / MS / MT / RO / TO
    'Vitória','Vila Velha','Cariacica','Serra','Campo Grande','Dourados',
    'Cuiabá','Várzea Grande','Porto Velho','Palmas',
  ].sort().filter((c, i, arr) => arr.indexOf(c) === i).map((c) => ({ value: c, label: c }))),
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

// Module-level cache — survives back navigation within same session
interface FilterCache {
  query: string;
  statusFilter: string;
  federationFilter?: number;
  countryFilter: string;
  categoryFilter: string;
  stateFilter: string;
  cityFilter: string;
  fromDate: string;
  toDate: string;
  modalityFilter: string;
  surfaceFilter: string;
  nearMe: boolean;
  showAdvanced: boolean;
}
let _filterCache: FilterCache | null = null;

export function TournamentsScreen({ route }: Props) {
  const { colors } = useTheme();
  const navigation = useNavigation<StackNav>();
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const tabBarHeight = useContext(BottomTabBarHeightContext) ?? 0;
  const flatListPadding = tabBarHeight > 0 ? tabBarHeight + 8 : insets.bottom + 16;

  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<TournamentEditionList[]>([]);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [calendarMap, setCalendarMap] = useState<Record<string, TournamentEditionList[]>>({});

  // Filters — restored from module-level cache on mount (survives back navigation)
  const c = _filterCache;
  const [query, setQuery] = useState(c?.query ?? '');
  const [statusFilter, setStatusFilter] = useState(c?.statusFilter ?? '');
  const [federations, setFederations] = useState<Organization[]>([]);
  const [federationFilter, setFederationFilter] = useState<number | undefined>(route.params?.organization ?? c?.federationFilter);
  const [countryFilter, setCountryFilter] = useState(c?.countryFilter ?? '');
  const [countryCodes, setCountryCodes] = useState<string[]>([]);
  const [categoryFilter, setCategoryFilter] = useState(c?.categoryFilter ?? '');
  const [stateFilter, setStateFilter] = useState(c?.stateFilter ?? '');
  const [cityFilter, setCityFilter] = useState(c?.cityFilter ?? '');
  const [fromDate, setFromDate] = useState(c?.fromDate ?? '');
  const [toDate, setToDate] = useState(c?.toDate ?? '');
  const [modalityFilter, setModalityFilter] = useState(c?.modalityFilter ?? '');
  const [surfaceFilter, setSurfaceFilter] = useState(c?.surfaceFilter ?? '');
  const [nearMe, setNearMe] = useState(c?.nearMe ?? false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);
  const [primaryProfile, setPrimaryProfile] = useState<PlayerProfile | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(c?.showAdvanced ?? false);

  // Calendar UI state
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [calMonth, setCalMonth] = useState(() => new Date());

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reloadVersion = useRef(0);

  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<number[]>([]);

  const appliedFilters = useMemo<TournamentFilters>(() => {
    const f: TournamentFilters = {};
    const trimmedQuery = query.trim();
    if (trimmedQuery) f.q = trimmedQuery;
    if (statusFilter) f.status = statusFilter;
    if (federationFilter) f.organization = federationFilter;
    if (countryFilter) f.country = countryFilter;
    if (categoryFilter) f.category = categoryFilter;
    if (stateFilter) f.state = stateFilter;
    if (cityFilter) f.city = cityFilter;
    if (fromDate && isValidIsoDate(fromDate)) f.from_date = fromDate;
    if (toDate && isValidIsoDate(toDate)) f.to_date = toDate;
    if (modalityFilter) f.modality = modalityFilter;
    if (surfaceFilter) f.surface = surfaceFilter;
    if (nearMe && primaryProfileId) f.near_profile = primaryProfileId;
    // Locked constraint: filter tournaments by the active profile's competitive level
    const level = (primaryProfile as any)?.competitive_level;
    if (level) f.player_level = level;
    return f;
  }, [
    query, statusFilter, federationFilter, countryFilter, categoryFilter,
    stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
    nearMe, primaryProfileId, primaryProfile,
  ]);

  const activeFilterCount = useMemo(() => {
    const filterKeys = Object.keys(appliedFilters).filter((key) => key !== 'q');
    return filterKeys.length;
  }, [appliedFilters]);

  const hasAnyFilter = useMemo(() => Object.keys(appliedFilters).length > 0, [appliedFilters]);
  const hasAnyInput = useMemo(() => !!(
    query || statusFilter || federationFilter || countryFilter || categoryFilter
    || stateFilter || cityFilter || fromDate || toDate || modalityFilter
    || surfaceFilter || nearMe
  ), [
    query, statusFilter, federationFilter, countryFilter, categoryFilter,
    stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
    nearMe,
  ]);

  // Country options grouped by name (Chile CHI/CHL → one item filtering both).
  const countryOptions = useMemo(() => {
    const byName = new Map<string, string[]>();
    for (const code of countryCodes) {
      const name = resolveCountry(code)?.name || code;
      const arr = byName.get(name) || [];
      arr.push(code);
      byName.set(name, arr);
    }
    const opts = [...byName.entries()].map(([name, codes]) => ({
      value: codes.join(','),
      label: name,
      isBrazil: codes.includes('BRA'),
    }));
    opts.sort((a, b) => {
      if (a.isBrazil) return -1;
      if (b.isBrazil) return 1;
      return a.label.localeCompare(b.label, 'pt-BR');
    });
    return opts.map(({ value, label }) => ({ value, label }));
  }, [countryCodes]);

  async function loadList(page = 1) {
    const myVersion = ++reloadVersion.current;
    if (page === 1) {
      setLoading(true);
      setError(null);
      setItems([]);
      setNextPage(null);
      setTotalCount(null);
    } else {
      setLoadingMore(true);
    }
    try {
      const data = await listEditions({
        ...appliedFilters,
        page,
        page_size: 20,
        ordering: 'status_priority,start_date',
      });
      if (myVersion !== reloadVersion.current) return;
      const results = sortTournaments(data.results || []);
      setItems((prev) => page === 1 ? results : [...prev, ...sortTournaments(results)]);
      setNextPage(data.next ? page + 1 : null);
      if (page === 1) setTotalCount(data.count ?? results.length);
    } catch {
      if (myVersion === reloadVersion.current) {
        if (page === 1) {
          setError('Não foi possível carregar os torneios. Verifique sua conexão e tente novamente.');
        } else {
          Toast.show({ type: 'error', text1: 'Erro ao carregar mais torneios' });
        }
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
    setError(null);
    try {
      const months = await calendar(appliedFilters);
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
        setError('Não foi possível carregar o calendário. Verifique sua conexão e tente novamente.');
      }
    } finally {
      if (myVersion === reloadVersion.current) setLoading(false);
    }
  }

  // Load active profile (for "Perto de mim" filter). Parent accounts only use
  // a dependent after explicit selection in Profile.
  useFocusEffect(
    useCallback(() => {
      let active = true;
      (async () => {
        try {
          const profiles = await listProfiles();
          const profileList = profiles as PlayerProfile[];
          const selectedProfileId = user?.role === 'parent' && user?.id ? await getActiveProfileId(user.id) : null;
          const selected = user?.role === 'parent'
            ? profileList.find((p) => p.id === selectedProfileId) ?? null
            : pickBestProfile(profileList);
          if (!active) return;
          setPrimaryProfileId(selected?.id ?? null);
          setPrimaryProfile(selected);
          if (!selected) setNearMe(false);
        } catch {
          if (!active) return;
          setPrimaryProfileId(null);
          setPrimaryProfile(null);
          setNearMe(false);
        }
      })();
      return () => { active = false; };
    }, [user?.id, user?.role]),
  );

  // Load federations once
  useEffect(() => {
    listFederations()
      .then(setFederations)
      .catch(() => setFederations([]));
    listCountries()
      .then(setCountryCodes)
      .catch(() => setCountryCodes([]));
  }, []);

  // Persist filters in module-level cache so they survive back navigation
  useEffect(() => {
    _filterCache = {
      query, statusFilter, federationFilter, countryFilter, categoryFilter,
      stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
      nearMe, showAdvanced,
    };
  }, [
    query, statusFilter, federationFilter, countryFilter, categoryFilter,
    stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
    nearMe, showAdvanced,
  ]);

  // Reload list/calendar whenever any filter or view mode changes (debounced for free-text fields)
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    const isTextFilter = !!(query || fromDate || toDate);
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
    viewMode, query, statusFilter, federationFilter, countryFilter, categoryFilter,
    stateFilter, cityFilter, fromDate, toDate, modalityFilter, surfaceFilter,
    nearMe, primaryProfileId,
  ]);

  // Apply incoming route params (deep-link / cross-screen navigation)
  useEffect(() => {
    if (route.params?.organization) setFederationFilter(route.params.organization);
  }, [route.params?.organization]);

  function clearFilters() {
    setQuery('');
    setCountryFilter('');
    setStatusFilter('');
    setFederationFilter(undefined);
    setCategoryFilter('');
    setStateFilter('');
    setCityFilter('');
    setFromDate('');
    setToDate('');
    setModalityFilter('');
    setSurfaceFilter('');
    setNearMe(false);
    _filterCache = null;
  }

  // Stable callbacks for FilterHeader — avoids creating new lambdas in render
  const handleFederationChange = useCallback((v: string) => setFederationFilter(v ? Number(v) : undefined), []);
  const handleFromDateChange   = useCallback((v: string) => setFromDate(formatIsoDateInput(v)), []);
  const handleToDateChange     = useCallback((v: string) => setToDate(formatIsoDateInput(v)), []);
  const handleToggleAdvanced   = useCallback(() => setShowAdvanced((v) => !v), []);
  const handleNearMeToggle     = useCallback(() => setNearMe((v) => !v), []);

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
  const organizationOptions = useMemo(
    () => [
      { value: '', label: 'Todas' },
      ...federations.map((org) => ({
        value: String(org.id),
        label: org.short_name ? `${org.short_name} - ${org.name}` : org.name,
      })),
    ],
    [federations],
  );

  const filterHeaderProps: FilterHeaderProps = {
    query, onQueryChange: setQuery,
    showAdvanced, onToggleAdvanced: handleToggleAdvanced,
    activeFilterCount, hasAnyInput, onClearFilters: clearFilters,
    statusFilter, onStatusChange: setStatusFilter,
    federationFilter, onFederationChange: handleFederationChange,
    organizationOptions,
    countryFilter, onCountryChange: setCountryFilter, countryOptions,
    categoryFilter, onCategoryChange: setCategoryFilter,
    stateFilter, onStateChange: setStateFilter,
    cityFilter, onCityChange: setCityFilter,
    fromDate, onFromDateChange: handleFromDateChange,
    toDate, onToDateChange: handleToDateChange,
    modalityFilter, onModalityChange: setModalityFilter,
    surfaceFilter, onSurfaceChange: setSurfaceFilter,
    nearMe, onNearMeToggle: handleNearMeToggle,
    primaryProfileId,
    primaryProfile,
    totalCount,
    loading,
  };

  const year = calMonth.getFullYear();
  const month = calMonth.getMonth();
  const firstDayOfMonth = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  function dayKey(day: number) { return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`; }
  const selectedDayItems = selectedDate ? (calendarMap[selectedDate] ?? []) : [];

  return (
    <Screen scroll={false}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, paddingHorizontal: 16 }}>
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
            <Pressable onPress={() => { setViewMode('calendar'); setShowAdvanced(false); setSelectedDate(null); }}
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
            ListHeaderComponent={<FilterHeader {...filterHeaderProps} />}
            ItemSeparatorComponent={() => <View style={{ height: 2 }} />}
            ListEmptyComponent={
              loading
                ? <TournamentListSkeleton count={6} />
                : error
                  ? (
                    <EmptyState
                      icon="cloud-offline-outline"
                      title="Não foi possível carregar"
                      subtitle={error}
                      action={<Button title="Tentar novamente" variant="ghost" onPress={() => loadList(1)} />}
                    />
                  )
                  : (
                    <EmptyState
                      title="Nenhum torneio encontrado."
                      subtitle={nearMe
                        ? 'Confira a cidade, UF e raio de viagem no seu perfil ou ajuste os filtros.'
                        : hasAnyFilter
                          ? 'Nenhum resultado para os filtros aplicados. Tente ampliar a busca.'
                          : 'Ainda não há torneios disponíveis. Volte em breve.'}
                    />
                  )
            }
            ListFooterComponent={loadingMore ? <TournamentListSkeleton count={2} /> : null}
            onEndReached={handleEndReached}
            onEndReachedThreshold={0.4}
            contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: flatListPadding }}
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
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 96 }}>
          <FilterHeader {...filterHeaderProps} />

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

          {loading ? <TournamentListSkeleton count={3} /> : error ? (
            <EmptyState
              icon="cloud-offline-outline"
              title="Não foi possível carregar"
              subtitle={error}
              action={<Button title="Tentar novamente" variant="ghost" onPress={loadCalendar} />}
            />
          ) : (
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
