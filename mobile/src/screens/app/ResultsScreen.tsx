import React, { useCallback, useState } from 'react';
import { View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { TournamentListSkeleton } from '../../components/Skeleton';
import { listWatchlist } from '../../services/data';
import { WatchlistItem } from '../../types';
import { Pressable } from 'react-native';

type Props = BottomTabScreenProps<MainTabParamList, 'Results'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

function ResultCard({ item, onPress }: { item: WatchlistItem; onPress: () => void }) {
  const { colors } = useTheme();
  const r = item.result!;

  const positionColor = () => {
    if (!r.position) return colors.textMuted;
    if (r.position === 1) return '#FFD700';
    if (r.position === 2) return '#C0C0C0';
    if (r.position === 3) return '#CD7F32';
    return colors.accentNeon;
  };

  const winRate = r.wins != null && r.losses != null && (r.wins + r.losses) > 0
    ? Math.round((r.wins / (r.wins + r.losses)) * 100)
    : null;

  return (
    <Pressable onPress={onPress} style={{ marginBottom: 12 }}>
      <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: colors.borderSubtle }}>
        {/* Header strip */}
        <View style={{ backgroundColor: `${colors.accentNeon}10`, paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="trophy-outline" size={14} color={colors.accentNeon} />
          <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', flex: 1 }} numberOfLines={1}>
            {item.edition_detail.title}
          </AppText>
          {item.edition_detail.start_date ? (
            <AppText variant="caption" style={{ color: colors.textMuted }}>
              {new Date(item.edition_detail.start_date).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })}
            </AppText>
          ) : null}
        </View>

        {/* Stats row */}
        <View style={{ flexDirection: 'row', padding: 14, gap: 8 }}>
          {/* Position */}
          {r.position != null ? (
            <View style={{ alignItems: 'center', backgroundColor: colors.bgBase, borderRadius: 12, padding: 12, flex: 1, borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 4 }}>Posição</AppText>
              <AppText variant="title" style={{ color: positionColor(), fontSize: 28 }}>
                {r.position === 1 ? '🥇' : r.position === 2 ? '🥈' : r.position === 3 ? '🥉' : `#${r.position}`}
              </AppText>
            </View>
          ) : null}

          {/* Wins / Losses */}
          {(r.wins != null || r.losses != null) ? (
            <View style={{ alignItems: 'center', backgroundColor: colors.bgBase, borderRadius: 12, padding: 12, flex: 1, borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 4 }}>V / D</AppText>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <AppText variant="body" style={{ color: colors.statusOpen, fontWeight: '700', fontSize: 18 }}>{r.wins ?? 0}</AppText>
                <AppText variant="muted" style={{ fontSize: 16 }}>/</AppText>
                <AppText variant="body" style={{ color: colors.statusCanceled, fontWeight: '700', fontSize: 18 }}>{r.losses ?? 0}</AppText>
              </View>
              {winRate != null ? (
                <AppText variant="caption" style={{ color: colors.textMuted, marginTop: 2 }}>{winRate}% vitórias</AppText>
              ) : null}
            </View>
          ) : null}

          {/* Category */}
          {r.category_played ? (
            <View style={{ alignItems: 'center', backgroundColor: colors.bgBase, borderRadius: 12, padding: 12, flex: 1, borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 4 }}>Categoria</AppText>
              <AppText variant="body" style={{ fontWeight: '700', textAlign: 'center', fontSize: 13 }} numberOfLines={2}>
                {r.category_played}
              </AppText>
            </View>
          ) : null}
        </View>

        {/* Notes */}
        {r.notes ? (
          <View style={{ paddingHorizontal: 14, paddingBottom: 12 }}>
            <AppText variant="muted" style={{ fontSize: 12, fontStyle: 'italic' }}>"{r.notes}"</AppText>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

export function ResultsScreen(_: Props) {
  const { colors } = useTheme();
  const navigation = useNavigation<Nav>();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const list = await listWatchlist();
      setItems((list as WatchlistItem[]).filter((item) => !!item.result));
    } catch {
      setError('Não foi possível carregar seus resultados agora.');
    } finally {
      setLoading(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const list = await listWatchlist();
      setItems((list as WatchlistItem[]).filter((item) => !!item.result));
    } catch {
      setError('Não foi possível atualizar seus resultados agora.');
    } finally {
      setRefreshing(false);
    }
  }

  useFocusEffect(useCallback(() => { load(); }, []));

  const totalWins   = items.reduce((sum, i) => sum + (i.result?.wins   ?? 0), 0);
  const totalLosses = items.reduce((sum, i) => sum + (i.result?.losses ?? 0), 0);
  const totalMatches = totalWins + totalLosses;

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <SectionHeader title="Resultados" subtitle="Torneios com resultado salvo" />

      {/* Summary stats */}
      {items.length > 0 && (
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 4 }}>
          {[
            { label: 'Torneios', value: items.length, color: colors.accentNeon },
            { label: 'Vitórias', value: totalWins, color: colors.statusOpen },
            { label: 'Derrotas', value: totalLosses, color: colors.statusCanceled },
            { label: 'Partidas', value: totalMatches, color: colors.accentBlue },
          ].map((s) => (
            <View key={s.label} style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 14, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="body" style={{ fontWeight: '800', fontSize: 20, color: s.color }}>{s.value}</AppText>
              <AppText variant="caption" style={{ fontSize: 10, textAlign: 'center', marginTop: 2 }}>{s.label}</AppText>
            </View>
          ))}
        </View>
      )}

      {loading ? (
        <TournamentListSkeleton count={3} />
      ) : error && items.length === 0 ? (
        <EmptyState
          title="Não foi possível carregar"
          subtitle={error}
          icon="cloud-offline-outline"
          action={
            <Pressable
              onPress={load}
              style={{ backgroundColor: `${colors.accentNeon}18`, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 8, borderWidth: 1, borderColor: `${colors.accentNeon}33` }}
            >
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Tentar novamente</AppText>
            </Pressable>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Nenhum resultado ainda"
          subtitle="Salve um resultado na agenda para ver seu histórico de torneios aqui."
          icon="trophy-outline"
          action={
            <Pressable
              onPress={() => navigation.navigate('Tabs', { screen: 'Watchlist' } as never)}
              style={{ backgroundColor: `${colors.accentNeon}18`, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 8, borderWidth: 1, borderColor: `${colors.accentNeon}33` }}
            >
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Ir para Agenda</AppText>
            </Pressable>
          }
        />
      ) : (
        items.map((item) => (
          <ResultCard
            key={item.id}
            item={item}
            onPress={() => navigation.navigate('TournamentDetail', { id: item.edition_detail.id, edition: item.edition_detail })}
          />
        ))
      )}
    </Screen>
  );
}
