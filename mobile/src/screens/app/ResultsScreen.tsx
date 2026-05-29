import React, { useCallback, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect } from '@react-navigation/native';
import Toast from 'react-native-toast-message';
import { MainTabParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { fetchTiData, listProfiles, syncTiData } from '../../services/data';
import { PlayerProfile, TiData } from '../../types';

type Props = BottomTabScreenProps<MainTabParamList, 'Results'>;

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

  const wins   = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W').length ?? 0;
  const losses = tiData?.results.filter((r) => r.outcome?.toUpperCase().startsWith('D')).length ?? 0;
  const total  = tiData?.results.length ?? 0;

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

  return (
    <Screen onRefresh={load} refreshing={tiSyncing}>
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <View style={{ flex: 1 }}>
          <SectionHeader title="Resultados" subtitle="Jogos importados automaticamente pelo Tênis Integrado" />
        </View>
        {tiData?.ti_id ? (
          <Pressable
            disabled={tiSyncing}
            hitSlop={8}
            onPress={handleSync}
            style={{ padding: 4, marginTop: 2 }}
          >
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
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
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

      {/* Conteúdo principal */}
      {tiLoading ? (
        <LoadingBlock />
      ) : !tiData?.has_ti_id ? (
        <EmptyState
          icon="link-outline"
          title="ID do Tênis Integrado não vinculado"
          subtitle="Vincule seu ID do Tênis Integrado no Perfil para importar jogos automaticamente."
        />
      ) : tiData.results.length === 0 ? (
        <EmptyState
          icon="tennisball-outline"
          title="Nenhum jogo encontrado"
          subtitle="Nenhum resultado foi encontrado no Tênis Integrado para este perfil."
        />
      ) : (
        <>
          {tiData.results.map((r, i) => {
            const isWin = r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W';
            return (
              <View
                key={i}
                style={{ backgroundColor: colors.bgCard, borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: colors.borderSubtle }}
              >
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                  <View style={{
                    width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: isWin ? `${colors.statusOpen}22` : `${colors.danger}22`,
                  }}>
                    <AppText variant="caption" style={{ fontWeight: '800', fontSize: 14, color: isWin ? colors.statusOpen : colors.danger }}>
                      {r.outcome ? r.outcome.slice(0, 1).toUpperCase() : '?'}
                    </AppText>
                  </View>
                  <View style={{ flex: 1, gap: 2 }}>
                    {r.tournament ? (
                      <AppText variant="caption" style={{ fontWeight: '600', fontSize: 13 }} numberOfLines={2}>{r.tournament}</AppText>
                    ) : null}
                    {r.opponent ? (
                      <AppText variant="muted" style={{ fontSize: 12 }}>vs {r.opponent}</AppText>
                    ) : null}
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                      {r.round    ? <AppText variant="muted" style={{ fontSize: 10 }}>{r.round}</AppText>    : null}
                      {r.category ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.category}</AppText> : null}
                      {r.score    ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.score}</AppText>    : null}
                      {r.date     ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.date}</AppText>     : null}
                    </View>
                  </View>
                </View>
              </View>
            );
          })}
          {tiData.is_stale ? (
            <AppText variant="muted" style={{ fontSize: 10, textAlign: 'center', marginTop: 4 }}>
              Dados podem estar desatualizados. Toque em ↻ para atualizar.
            </AppText>
          ) : null}
        </>
      )}
    </Screen>
  );
}
