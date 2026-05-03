import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { checkConflicts, ConflictPair, getEdition } from '../../services/tournaments';
import { TournamentEditionDetail } from '../../types';
import { fmtBRL, fmtDate, fmtDateRange, STATUS_LABELS } from '../../utils/format';
import { useTheme } from '../../contexts/ThemeContext';

type CompareRouteProp = RouteProp<MainStackParamList, 'TournamentCompare'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

const FIELD_ROWS = [
  { key: 'status',       label: 'Status',        render: (d: TournamentEditionDetail) => STATUS_LABELS[d.status] ?? d.status },
  { key: 'dates',        label: 'Datas',          render: (d: TournamentEditionDetail) => fmtDateRange(d.start_date, d.end_date) },
  { key: 'deadline',     label: 'Prazo de inscrição', render: (d: TournamentEditionDetail) => fmtDate(d.entry_close_at) },
  { key: 'location',     label: 'Local',          render: (d: TournamentEditionDetail) => d.venue_city && d.venue_state ? `${d.venue_city} – ${d.venue_state}` : d.venue_name ?? '—' },
  { key: 'price',        label: 'Valor',          render: (d: TournamentEditionDetail) => d.base_price_brl ? fmtBRL(d.base_price_brl) : '—' },
  { key: 'categories',   label: 'Categorias',     render: (d: TournamentEditionDetail) => String(d.categories?.length ?? 0) },
  { key: 'circuit',      label: 'Circuito',       render: (d: TournamentEditionDetail) => d.circuit || d.organization_short || '—' },
  { key: 'surface',      label: 'Quadra',         render: (d: TournamentEditionDetail) => d.surface || '—' },
  { key: 'confidence',   label: 'Qualidade dos dados', render: (d: TournamentEditionDetail) => ({ low: 'Baixa', med: 'Média', medium: 'Média', high: 'Alta' }[d.data_confidence] ?? '—') },
];

function ColHeader({ detail, onPress }: { detail: TournamentEditionDetail; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <TouchableOpacity style={styles.colHeader} onPress={onPress}>
      <Text style={[styles.colTitle, { color: colors.textPrimary }]} numberOfLines={2}>{detail.title}</Text>
      <Text style={[styles.colOrg, { color: colors.textMuted }]}>{detail.organization_name}</Text>
    </TouchableOpacity>
  );
}

export function TournamentCompareScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<CompareRouteProp>();
  const { ids } = route.params;
  const { colors } = useTheme();

  const [details, setDetails] = useState<(TournamentEditionDetail | null)[]>([]);
  const [conflicts, setConflicts] = useState<ConflictPair[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      Promise.all(ids.map((id) => getEdition(id).catch(() => null))),
      checkConflicts(ids).catch(() => ({ conflicts: [], has_conflicts: false })),
    ])
      .then(([detailResults, conflictResult]) => {
        setDetails(detailResults);
        setConflicts(conflictResult.conflicts);
      })
      .catch(() => Alert.alert('Erro', 'Não foi possível carregar os torneios.'))
      .finally(() => setLoading(false));
  }, [ids]);

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: colors.bgBase }]}>
        <ActivityIndicator size="large" color={colors.accentNeon} />
      </View>
    );
  }

  const loaded = details.filter(Boolean) as TournamentEditionDetail[];
  if (loaded.length === 0) {
    return (
      <View style={[styles.center, { backgroundColor: colors.bgBase }]}>
        <Text style={{ color: colors.textPrimary }}>Nenhum torneio encontrado.</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.bgBase }]}
      contentContainerStyle={styles.content}
      horizontal={false}
    >
      {/* Column headers */}
      <View style={styles.headerRow}>
        <View style={styles.labelCol} />
        {loaded.map((d) => (
          <ColHeader
            key={d.id}
            detail={d}
            onPress={() => navigation.navigate('TournamentDetail', { id: d.id, edition: d })}
          />
        ))}
      </View>

      {/* Conflict warning */}
      {conflicts.length > 0 && (
        <View style={[styles.conflictBanner, { backgroundColor: '#7c2d12', borderColor: '#ea580c' }]}>
          <Ionicons name="warning-outline" size={16} color="#fb923c" />
          <View style={{ flex: 1, marginLeft: 8 }}>
            <Text style={{ color: '#fb923c', fontWeight: '700', fontSize: 13 }}>Conflito de datas detectado</Text>
            {conflicts.map((c, i) => (
              <Text key={i} style={{ color: '#fed7aa', fontSize: 12, marginTop: 2 }}>
                "{c.edition_a.title}" e "{c.edition_b.title}" têm datas sobrepostas.
              </Text>
            ))}
          </View>
        </View>
      )}

      {/* Data rows */}
      {FIELD_ROWS.map((row, idx) => (
        <View
          key={row.key}
          style={[styles.dataRow, { backgroundColor: idx % 2 === 0 ? colors.bgSubtle : colors.bgBase }]}
        >
          <Text style={[styles.labelText, { color: colors.textMuted }]}>{row.label}</Text>
          {loaded.map((d) => (
            <Text key={d.id} style={[styles.valueText, { color: colors.textPrimary }]}>
              {row.render(d)}
            </Text>
          ))}
        </View>
      ))}

      {/* Categories breakdown */}
      <View style={[styles.sectionHeader, { backgroundColor: colors.bgSubtle }]}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>Categorias</Text>
      </View>
      <View style={styles.headerRow}>
        <View style={styles.labelCol} />
        {loaded.map((d) => (
          <View key={d.id} style={styles.colData}>
            {d.categories?.length ? d.categories.map((c) => (
              <Text key={c.id} style={[styles.categoryChip, { color: colors.textSecondary }]}>
                • {c.source_category_text}
                {c.price_brl ? `  (${fmtBRL(c.price_brl)})` : ''}
              </Text>
            )) : <Text style={{ color: colors.textMuted }}>—</Text>}
          </View>
        ))}
      </View>

      {/* Official links */}
      <View style={[styles.sectionHeader, { backgroundColor: colors.bgSubtle }]}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>Links oficiais</Text>
      </View>
      <View style={styles.headerRow}>
        <View style={styles.labelCol} />
        {loaded.map((d) => (
          <View key={d.id} style={styles.colData}>
            {d.official_source_url ? (
              <TouchableOpacity onPress={() => Linking.openURL(d.official_source_url)}>
                <View style={styles.linkRow}>
                  <Ionicons name="open-outline" size={14} color={colors.accentNeon} />
                  <Text style={[styles.linkText, { color: colors.accentNeon }]}>Abrir fonte oficial</Text>
                </View>
              </TouchableOpacity>
            ) : (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>Não disponível</Text>
            )}
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content:   { paddingBottom: 40 },
  center:    { flex: 1, justifyContent: 'center', alignItems: 'center' },

  headerRow:  { flexDirection: 'row', paddingHorizontal: 8, paddingVertical: 10 },
  labelCol:   { width: 90 },
  colHeader:  { flex: 1, paddingHorizontal: 6 },
  colTitle:   { fontSize: 13, fontWeight: '700', marginBottom: 2 },
  colOrg:     { fontSize: 11 },

  dataRow:    { flexDirection: 'row', paddingHorizontal: 8, paddingVertical: 10, alignItems: 'flex-start' },
  labelText:  { width: 90, fontSize: 12, paddingRight: 4 },
  colData:    { flex: 1, paddingHorizontal: 6 },
  valueText:  { flex: 1, fontSize: 13, paddingHorizontal: 6 },

  sectionHeader: { paddingHorizontal: 16, paddingVertical: 8, marginTop: 8 },
  sectionTitle:  { fontSize: 14, fontWeight: '700' },

  categoryChip: { fontSize: 12, marginBottom: 3 },

  linkRow:  { flexDirection: 'row', alignItems: 'center', gap: 4 },
  linkText: { fontSize: 12, textDecorationLine: 'underline' },

  conflictBanner: {
    flexDirection: 'row', alignItems: 'flex-start',
    marginHorizontal: 8, marginVertical: 8,
    padding: 12, borderRadius: 8, borderWidth: 1,
  },
});
