import React, { useCallback, useState } from 'react';
import { Linking, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import Toast from 'react-native-toast-message';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Card, EmptyState, LoadingBlock, Screen } from '../../components/ui';
import { FederationCategoryGroup, FederationEntry } from '../../types';
import { federationRegistrations } from '../../services/registrations';
import { fmtDateTime, tenisIntegradoId, tenisIntegradoProfileUrl } from '../../utils/format';

type Props = NativeStackScreenProps<MainStackParamList, 'RegistrationList'>;

// Status display config — all possible backend values
type ThemeColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

function getStatusConfig(c: ThemeColors): Record<string, { color: string; icon: string; label: string; detail?: string }> {
  return {
    confirmed:       { color: c.statusOpen,    icon: 'checkmark-circle',   label: 'Confirmado na chave' },
    waiting_list:    { color: c.statusClosing, icon: 'time',               label: 'Lista de espera' },
    pending_payment: { color: c.accentBlue,    icon: 'card-outline',       label: 'Aguardando pagamento' },
    registered:      { color: c.statusClosed,  icon: 'person-add-outline', label: 'Inscrito' },
    removed: {
      color: c.danger,
      icon: 'close-circle',
      label: 'Removido',
      detail: 'Atleta removido por critério de ranking da federação. Um atleta com ranking superior se inscreveu após o preenchimento das vagas.',
    },
  };
}

function getPaymentColors(c: ThemeColors): Record<string, string> {
  return {
    paid:    c.statusOpen,
    pending: c.statusClosing,
    unknown: c.statusClosed,
  };
}

function getConfidenceConfig(c: ThemeColors): Record<string, { icon: string; color: string; label: string }> {
  return {
    high:   { icon: 'shield-checkmark-outline',    color: c.statusOpen,    label: 'Fonte oficial' },
    medium: { icon: 'information-circle-outline',  color: c.statusClosing, label: 'Fonte pública' },
    low:    { icon: 'alert-circle-outline',         color: c.danger,        label: 'Dado inferido' },
  };
}

const STALE_HOURS = 24;

function isStale(syncedAt: string | null): boolean {
  if (!syncedAt) return false;
  return (Date.now() - new Date(syncedAt).getTime()) > STALE_HOURS * 3600 * 1000;
}

export function RegistrationListScreen({ route, navigation }: Props) {
  const { colors } = useTheme();
  const { editionId, editionTitle } = route.params;
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [categories, setCategories] = useState<FederationCategoryGroup[]>([]);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  const [sourceLabel, setSourceLabel] = useState<string>('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [error, setError] = useState(false);

  const loadData = useCallback(async () => {
    setError(false);
    try {
      const data = await federationRegistrations(editionId);
      setCategories(data.categories);
      const firstEntry = data.categories[0]?.entries[0];
      if (firstEntry) {
        setSyncedAt(firstEntry.synced_at);
        setSourceLabel(firstEntry.source_label || firstEntry.source);
      }
      if (data.categories.length > 0) {
        setExpanded(new Set([data.categories[0].category_text]));
      }
    } catch {
      setError(true);
      Toast.show({ type: 'error', text1: 'Erro ao carregar lista de inscritos' });
    }
  }, [editionId]);

  React.useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [loadData]);

  async function onRefresh() {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  }

  function toggleCategory(text: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(text)) next.delete(text);
      else next.add(text);
      return next;
    });
  }

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <AppText variant="body" style={{ fontWeight: '700' }}>Lista de inscritos</AppText>
          <AppText variant="caption" numberOfLines={1}>{editionTitle}</AppText>
        </View>
      </View>

      {/* Staleness warning */}
      {isStale(syncedAt) && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: `${colors.statusClosing}15`, borderWidth: 1, borderColor: `${colors.statusClosing}40`, borderRadius: 10, padding: 10, marginBottom: 8 }}>
          <Ionicons name="warning-outline" size={14} color={colors.statusClosing} />
          <AppText variant="caption" style={{ color: colors.statusClosing, flex: 1 }}>
            Dados com mais de {STALE_HOURS}h. Toque para atualizar.
          </AppText>
          <Pressable onPress={onRefresh}><Ionicons name="refresh" size={14} color={colors.statusClosing} /></Pressable>
        </View>
      )}

      {/* Sync info bar */}
      {(syncedAt || sourceLabel) ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6, paddingHorizontal: 2, marginBottom: 4 }}>
          <Ionicons name="sync-outline" size={13} color={colors.textMuted} />
          <AppText variant="muted" style={{ fontSize: 11 }}>
            {sourceLabel ? `Fonte: ${sourceLabel}` : ''}
            {sourceLabel && syncedAt ? ' · ' : ''}
            {syncedAt ? `Atualizado em ${fmtDateTime(syncedAt)}` : ''}
          </AppText>
        </View>
      ) : null}

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <EmptyState
          title="Erro ao carregar inscritos"
          subtitle="Verifique sua conexão e puxe para atualizar."
          icon="alert-circle-outline"
        />
      ) : categories.length === 0 ? (
        <EmptyState
          title="Lista ainda não publicada"
          subtitle="A federação ainda não divulgou as inscrições deste torneio. Tente novamente mais tarde ou consulte o site oficial."
          icon="people-outline"
        />
      ) : (
        categories.map((cat) => (
          <CategorySection
            key={cat.category_text}
            cat={cat}
            expanded={expanded.has(cat.category_text)}
            onToggle={() => toggleCategory(cat.category_text)}
            colors={colors}
          />
        ))
      )}

      {/* Note about ranking replacement rule */}
      <Card style={{ backgroundColor: `${colors.accentBlue}10`, borderColor: `${colors.accentBlue}30`, borderWidth: 1 }}>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Ionicons name="information-circle-outline" size={16} color={colors.accentBlue} />
          <AppText variant="muted" style={{ flex: 1, fontSize: 11, lineHeight: 16 }}>
            O status "Confirmado na chave" indica que o atleta está confirmado conforme os dados publicados pela federação. Em torneios com critério de ranking, um atleta pago pode ser substituído se um atleta com ranking superior se inscrever após o preenchimento das vagas.
          </AppText>
        </View>
      </Card>
    </Screen>
  );
}

function CategorySection({
  cat, expanded, onToggle, colors,
}: {
  cat: FederationCategoryGroup;
  expanded: boolean;
  onToggle: () => void;
  colors: ThemeColors;
}) {
  const { summary } = cat;
  const totalSlots = summary.total_slots ?? cat.max_participants;
  const drawFull = totalSlots != null && summary.filled_slots >= totalSlots;
  // Detect COSAT source from first entry — payment info not available for COSAT
  const isCosatSource = cat.entries[0]?.source === 'cosat';

  return (
    <Card style={{ padding: 0, overflow: 'hidden' }}>
      {/* Category header */}
      <Pressable
        onPress={onToggle}
        style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14 }}
      >
        <View style={{ flex: 1 }}>
          <AppText variant="body" style={{ fontWeight: '700' }}>{cat.category_text}</AppText>
          {totalSlots != null ? (
            <AppText variant="caption" style={{ marginTop: 2 }}>
              {`Vagas: ${summary.filled_slots}/${totalSlots}`}
              {drawFull ? ' · Chave completa' : ` · ${summary.remaining_slots ?? (totalSlots - summary.filled_slots)} restante${(summary.remaining_slots ?? 1) !== 1 ? 's' : ''}`}
            </AppText>
          ) : null}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
      </Pressable>

      {/* Summary pills — COSAT: show only total (payment not tracked by source) */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: 14, paddingBottom: 12 }}>
        {isCosatSource ? (
          <>
            <View style={{ backgroundColor: `${colors.textMuted}18`, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: 1, borderColor: `${colors.textMuted}40` }}>
              <AppText variant="caption" style={{ color: colors.textMuted, fontWeight: '600', fontSize: 11 }}>
                {summary.total} inscrito{summary.total !== 1 ? 's' : ''}
              </AppText>
            </View>
            <View style={{ backgroundColor: `${colors.textMuted}10`, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: 1, borderColor: `${colors.textMuted}25` }}>
              <AppText variant="caption" style={{ color: colors.textMuted, fontStyle: 'italic', fontSize: 11 }}>
                Pagamento não informado pela fonte
              </AppText>
            </View>
          </>
        ) : (
          [
            { label: `${summary.total} inscrito${summary.total !== 1 ? 's' : ''}`, color: colors.textMuted },
            { label: `${summary.in_draw} na chave`,                                 color: colors.statusOpen },
            { label: `${summary.paid} pago${summary.paid !== 1 ? 's' : ''}`,        color: colors.accentBlue },
            { label: `${summary.pending} pendente${summary.pending !== 1 ? 's' : ''}`, color: colors.statusClosing },
          ].map((pill) => (
            <View key={pill.label} style={{ backgroundColor: `${pill.color}18`, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: 1, borderColor: `${pill.color}40` }}>
              <AppText variant="caption" style={{ color: pill.color, fontWeight: '600', fontSize: 11 }}>{pill.label}</AppText>
            </View>
          ))
        )}
      </View>

      {/* Entry list */}
      {expanded && (
        <View style={{ borderTopWidth: 1, borderTopColor: colors.borderSubtle }}>
          {cat.entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} maxP={totalSlots} colors={colors} />
          ))}
        </View>
      )}
    </Card>
  );
}

function EntryRow({ entry, maxP, colors }: { entry: FederationEntry; maxP: number | null; colors: ThemeColors }) {
  const STATUS_CONFIG = getStatusConfig(colors);
  const PAYMENT_COLORS = getPaymentColors(colors);
  const CONFIDENCE_CONFIG = getConfidenceConfig(colors);
  const sc = STATUS_CONFIG[entry.status] ?? { color: colors.statusClosed, icon: 'help-circle-outline', label: 'Status não disponível' };
  const payColor = PAYMENT_COLORS[entry.payment_status] ?? colors.statusClosed;
  const confCfg = CONFIDENCE_CONFIG[entry.confidence] ?? CONFIDENCE_CONFIG.medium;
  const isRemoved = entry.status === 'removed';
  // COSAT: payment is not tracked — hide payment badge to avoid misleading "Não informado"
  const showPaymentBadge = entry.source !== 'cosat' && entry.status !== 'registered';

  return (
    <View style={{
      paddingHorizontal: 14,
      paddingVertical: 12,
      borderBottomWidth: 1,
      borderBottomColor: colors.borderSubtle,
      backgroundColor: isRemoved ? `${sc.color}06` : 'transparent',
      opacity: isRemoved ? 0.85 : 1,
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start' }}>
        {/* Slot position */}
        <View style={{ width: 36, alignItems: 'center', paddingTop: 2 }}>
          <AppText variant="caption" style={{ fontWeight: '700', fontSize: 14, color: isRemoved ? sc.color : (entry.in_draw ? colors.statusOpen : colors.textMuted) }}>
            {entry.slot_position != null ? `#${entry.slot_position}` : '—'}
          </AppText>
        </View>

        {/* Player info */}
        <View style={{ flex: 1, marginLeft: 8 }}>
          <AppText variant="body" style={{ fontWeight: '600', textDecorationLine: isRemoved ? 'line-through' : 'none' }}>
            {entry.player_name}
          </AppText>
          {entry.player_country_name ? (
            <AppText variant="caption" style={{ color: colors.textMuted, fontSize: 11, marginTop: 1 }}>
              {entry.player_country_name}
            </AppText>
          ) : null}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2, flexWrap: 'wrap' }}>
            {entry.ranking_position != null ? (
              <AppText variant="caption" style={{ color: colors.textMuted }}>
                Ranking {entry.ranking_position}
              </AppText>
            ) : null}
            {tenisIntegradoId(entry.player_external_id) ? (
              <Pressable onPress={() => Linking.openURL(tenisIntegradoProfileUrl(entry.player_external_id)!)}>
                <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>
                  ID TI {tenisIntegradoId(entry.player_external_id)}
                </AppText>
              </Pressable>
            ) : null}
            {entry.player_uf ? (
              <AppText variant="caption" style={{ color: colors.textMuted }}>· {entry.player_uf}</AppText>
            ) : null}
            {entry.player_age != null ? (
              <AppText variant="caption" style={{ color: colors.textMuted }}>· {entry.player_age} anos</AppText>
            ) : null}
            {entry.notes ? (
              <AppText variant="caption" style={{ color: colors.textMuted }}>· {entry.notes}</AppText>
            ) : null}
          </View>

          {/* Removed reason */}
          {isRemoved && entry.replacement_reason ? (
            <AppText variant="muted" style={{ fontSize: 11, marginTop: 4, color: sc.color, lineHeight: 15 }}>
              {entry.replacement_reason}
            </AppText>
          ) : null}
          {isRemoved && !entry.replacement_reason ? (
            <AppText variant="muted" style={{ fontSize: 11, marginTop: 4, color: sc.color }}>
              Removido por critério de ranking da federação
            </AppText>
          ) : null}
        </View>

        {/* Status column */}
        <View style={{ alignItems: 'flex-end', gap: 4, marginLeft: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name={sc.icon as any} size={14} color={sc.color} />
            <AppText variant="caption" style={{ color: sc.color, fontWeight: '600', fontSize: 10 }}>
              {sc.label}
            </AppText>
          </View>
          {showPaymentBadge && (
            <View style={{ backgroundColor: `${payColor}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
              <AppText variant="caption" style={{ color: payColor, fontWeight: '600', fontSize: 10 }}>
                {entry.payment_status_label}
              </AppText>
            </View>
          )}
          {/* Confidence indicator */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
            <Ionicons name={confCfg.icon as any} size={10} color={confCfg.color} />
            <AppText variant="muted" style={{ fontSize: 9, color: confCfg.color }}>{confCfg.label}</AppText>
          </View>
        </View>
      </View>

      {entry.source_url ? (
        <Pressable onPress={() => {
          const raw = entry.source_url as string;
          if (raw.trim().startsWith('http://') || raw.trim().startsWith('https://')) {
            Linking.canOpenURL(raw).then(supported => {
              if (supported) Linking.openURL(raw).catch(() => Toast.show({ type: 'error', text1: 'Não foi possível abrir o link' }));
              else Toast.show({ type: 'error', text1: 'Não foi possível abrir o link' });
            }).catch(() => Toast.show({ type: 'error', text1: 'Não foi possível abrir o link' }));
          } else {
            Toast.show({ type: 'error', text1: 'Link inválido' });
          }
        }} style={{ marginTop: 6, marginLeft: 44, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Ionicons name="open-outline" size={11} color={colors.accentBlue} />
          <AppText variant="muted" style={{ fontSize: 10, color: colors.accentBlue }}>Ver na fonte oficial</AppText>
        </Pressable>
      ) : null}
    </View>
  );
}
