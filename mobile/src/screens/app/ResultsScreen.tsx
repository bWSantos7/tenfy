import React, { useCallback, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect } from '@react-navigation/native';
import Toast from 'react-native-toast-message';
import { MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { fetchTiData, listProfiles, syncTiData } from '../../services/data';
import { PlayerProfile, TiData, TiResultEntry } from '../../types';

type Props = BottomTabScreenProps<MainTabParamList, 'Results'>;

// ── helpers ───────────────────────────────────────────────────────────────────

interface TournamentGroup {
  key: string;
  tournament: string;
  date: string;
  federation: string;
  matches: TiResultEntry[];
}

function groupByTournament(results: TiResultEntry[]): TournamentGroup[] {
  const groups: TournamentGroup[] = [];
  const index: Record<string, number> = {};
  for (const r of results) {
    const key = `${r.tournament}||${r.date}`;
    if (key in index) {
      groups[index[key]].matches.push(r);
    } else {
      index[key] = groups.length;
      groups.push({ key, tournament: r.tournament ?? '', date: r.date ?? '', federation: r.federation ?? '', matches: [r] });
    }
  }
  return groups;
}

// ── screen ────────────────────────────────────────────────────────────────────

export function ResultsScreen(_: Props) {
  const { colors } = useTheme();
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(true);
  const [tiSyncing, setTiSyncing] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);

  async function load() {
    setTiLoading(true);
    try {
      const profs = await listProfiles().catch(() => [] as PlayerProfile[]);
      const primary = (profs as PlayerProfile[]).find((p) => p.is_primary) ?? (profs as PlayerProfile[])[0];
      if (primary) {
        setPrimaryProfileId(primary.id);
        const data = await fetchTiData(primary.id);
        setTiData(data);
      }
    } catch {
      // handled per-section below
    } finally {
      setTiLoading(false);
    }
  }

  useFocusEffect(useCallback(() => { load(); }, []));

  async function handleSync() {
    if (!primaryProfileId) return;
    setTiSyncing(true);
    try {
      await syncTiData(primaryProfileId);
      const fresh = await fetchTiData(primaryProfileId);
      setTiData(fresh);
    } catch {
      Toast.show({ type: 'error', text1: 'Não foi possível atualizar agora.' });
    } finally {
      setTiSyncing(false);
    }
  }

  const groups  = groupByTournament(tiData?.results ?? []);
  const wins    = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W').length ?? 0;
  const losses  = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('D')).length ?? 0;
  const total   = tiData?.results.length ?? 0;

  return (
    <Screen onRefresh={load} refreshing={tiSyncing}>
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
        <SectionHeader title="Resultados" subtitle="Jogos importados automaticamente pelo Tênis Integrado" />
        {tiData?.ti_id ? (
          <Pressable disabled={tiSyncing} hitSlop={8} onPress={handleSync} style={{ padding: 4, marginTop: 2 }}>
            <Ionicons
              name={tiSyncing ? 'refresh' : 'refresh-outline'}
              size={18}
              color={tiSyncing ? colors.accentNeon : colors.textMuted}
            />
          </Pressable>
        ) : null}
      </View>

      {/* Stats */}
      {tiData?.has_ti_id && total > 0 && (
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
          {[
            { label: 'Jogos',    value: total,  color: colors.accentBlue     },
            { label: 'Vitórias', value: wins,   color: colors.statusOpen     },
            { label: 'Derrotas', value: losses, color: colors.statusCanceled },
          ].map((s) => (
            <View key={s.label} style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 14, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="body" style={{ fontWeight: '800', fontSize: 18, color: s.color }}>{s.value}</AppText>
              <AppText variant="caption" style={{ fontSize: 10, textAlign: 'center', marginTop: 2 }}>{s.label}</AppText>
            </View>
          ))}
        </View>
      )}

      {/* Content */}
      {tiLoading ? (
        <LoadingBlock />

      ) : !tiData?.has_ti_id ? (
        <EmptyState
          icon="link-outline"
          title="ID do Tênis Integrado não vinculado"
          subtitle="Vincule seu ID do Tênis Integrado no Perfil para importar jogos automaticamente."
        />

      ) : groups.length === 0 ? (
        <EmptyState
          icon="tennisball-outline"
          title="Nenhum jogo encontrado"
          subtitle="Nenhum resultado foi encontrado no Tênis Integrado para este perfil."
        />

      ) : (
        <>
          {groups.map((g) => (
            <View
              key={g.key}
              style={{ backgroundColor: colors.bgCard, borderRadius: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.borderSubtle, overflow: 'hidden' }}
            >
              {/* Tournament header */}
              <View style={{ paddingHorizontal: 14, paddingVertical: 10, backgroundColor: `${colors.bgElevated}CC`, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}>
                <AppText variant="caption" style={{ fontWeight: '700', fontSize: 13, lineHeight: 18 }} numberOfLines={2}>
                  {g.tournament}
                </AppText>
                {g.date ? (
                  <AppText variant="muted" style={{ fontSize: 11, marginTop: 2 }}>{g.date}</AppText>
                ) : null}
                {g.federation ? (
                  <View style={{ alignSelf: 'flex-start', marginTop: 6, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 20, backgroundColor: `${colors.accentBlue}22` }}>
                    <AppText variant="muted" style={{ fontSize: 10, color: colors.accentBlue, fontWeight: '600' }}>{g.federation}</AppText>
                  </View>
                ) : null}
              </View>

              {/* Match rows */}
              {g.matches.map((m, i) => {
                const isWin = m.outcome?.toUpperCase().startsWith('V') || m.outcome?.toUpperCase() === 'W';
                return (
                  <View
                    key={i}
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 10,
                      paddingHorizontal: 14, paddingVertical: 10,
                      borderTopWidth: i === 0 ? 0 : 1, borderTopColor: colors.borderSubtle,
                    }}
                  >
                    {/* Phase */}
                    <AppText variant="muted" style={{ width: 30, fontSize: 11, fontWeight: '600' }}>
                      {m.round ?? '—'}
                    </AppText>

                    {/* Opponent */}
                    <AppText variant="caption" style={{ flex: 1, fontSize: 12 }} numberOfLines={1}>
                      {m.opponent ?? '—'}
                    </AppText>

                    {/* Outcome badge */}
                    <View style={{
                      width: 24, height: 24, borderRadius: 12,
                      alignItems: 'center', justifyContent: 'center',
                      backgroundColor: isWin ? `${colors.statusOpen}22` : `${colors.danger}22`,
                    }}>
                      <AppText variant="caption" style={{ fontSize: 11, fontWeight: '800', color: isWin ? colors.statusOpen : colors.danger }}>
                        {m.outcome ? m.outcome.slice(0, 1).toUpperCase() : '?'}
                      </AppText>
                    </View>

                    {/* Score */}
                    {m.score ? (
                      <AppText variant="muted" style={{ fontSize: 11, minWidth: 60, textAlign: 'right' }}>
                        {m.score}
                      </AppText>
                    ) : null}
                  </View>
                );
              })}
            </View>
          ))}

          {tiData?.is_stale ? (
            <AppText variant="muted" style={{ fontSize: 10, textAlign: 'center', marginTop: 4 }}>
              Dados podem estar desatualizados. Toque em ↻ para atualizar.
            </AppText>
          ) : null}
        </>
      )}
    </Screen>
  );
}
