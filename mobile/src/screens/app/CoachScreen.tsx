import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { addAthlete, getAthleteWatchlist, listAthletes, removeAthlete } from '../../services/data';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { CoachAthlete, WatchlistItem } from '../../types';
import { extractApiError } from '../../services/api';
import { fmtDate, STATUS_LABELS } from '../../utils/format';

type Props = NativeStackScreenProps<MainStackParamList, 'Coach'>;

const USER_STATUS_LABELS: Record<string, string> = {
  none: 'Acompanhando',
  intended: 'Pretende inscrever',
  registered_declared: 'Inscrito',
  withdrawn: 'Desistiu',
  completed: 'Concluído',
};
type ThemeColors = ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];

function getUserStatusColors(c: ThemeColors): Record<string, string> {
  return {
    none:                c.statusClosed,
    intended:           c.accentBlue,
    registered_declared: c.statusOpen,
    withdrawn:          c.danger,
    completed:          c.statusProgress,
  };
}

export function CoachScreen(_: Props) {
  const { colors } = useTheme();
  const navigation = useNavigation<any>();
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [adding, setAdding] = useState(false);
  const [athletes, setAthletes] = useState<CoachAthlete[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [watchlists, setWatchlists] = useState<Record<number, { athlete: string; watchlist: WatchlistItem[] }>>({});
  const [loadingWl, setLoadingWl] = useState<Record<number, boolean>>({});

  async function load() {
    setLoading(true);
    try {
      setAthletes(await listAthletes().catch(() => []) as CoachAthlete[]);
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao carregar alunos' });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function onAdd() {
    if (!email.trim()) return;
    setAdding(true);
    try {
      await addAthlete(email.trim().toLowerCase());
      setEmail('');
      await load();
      Toast.show({ type: 'success', text1: 'Aluno adicionado.' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Não foi possível adicionar o aluno.', text2: extractApiError(err) });
    } finally {
      setAdding(false);
    }
  }

  function onRemove(link: CoachAthlete) {
    Alert.alert(
      'Remover aluno',
      `Tem certeza que deseja remover ${link.athlete_detail.full_name || link.athlete_detail.email} da sua lista?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeAthlete(link.id);
              await load();
              if (expandedId === link.id) setExpandedId(null);
              Toast.show({ type: 'success', text1: 'Aluno removido.' });
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Não foi possível remover o aluno.', text2: extractApiError(err) });
            }
          },
        },
      ],
    );
  }

  async function toggleWatchlist(link: CoachAthlete) {
    const id = link.id;
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (watchlists[id]) return;
    setLoadingWl((prev) => ({ ...prev, [id]: true }));
    try {
      const data = await getAthleteWatchlist(id);
      setWatchlists((prev) => ({ ...prev, [id]: data }));
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Não foi possível carregar a agenda.', text2: extractApiError(err) });
    } finally {
      setLoadingWl((prev) => ({ ...prev, [id]: false }));
    }
  }

  return (
    <Screen scroll={false}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <View>
          <AppText variant="title">Meus alunos</AppText>
          <AppText variant="muted">Gerencie os atletas vinculados à sua conta</AppText>
        </View>
      </View>

      <Card style={{ marginBottom: 12 }}>
        <AppText variant="body" style={{ fontWeight: '700', marginBottom: 8 }}>Adicionar aluno</AppText>
        <Input
          label="E-mail do atleta"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="atleta@email.com"
        />
        <Button title={adding ? 'Adicionando...' : 'Adicionar'} onPress={onAdd} loading={adding} />
      </Card>

      <AppText variant="section" style={{ marginBottom: 8 }}>
        {athletes.length > 0 ? `${athletes.length} aluno${athletes.length > 1 ? 's' : ''}` : 'Nenhum aluno ainda'}
      </AppText>

      {loading ? <LoadingBlock /> : athletes.length === 0 ? (
        <EmptyState
          title="Nenhum aluno adicionado."
          subtitle="Adicione atletas pelo e-mail para acompanhar a agenda deles."
        />
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 16 }}>
          {athletes.map((link) => {
            const isExpanded = expandedId === link.id;
            const wlData = watchlists[link.id];
            const isLoadingWl = loadingWl[link.id];
            const name = link.athlete_detail.full_name || link.athlete_detail.email;
            return (
              <View key={link.id} style={{ marginBottom: 8 }}>
                <Card>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.accentNeon}20`, alignItems: 'center', justifyContent: 'center' }}>
                      <AppText variant="body" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 16 }}>
                        {name[0].toUpperCase()}
                      </AppText>
                    </View>
                    <View style={{ flex: 1 }}>
                      <AppText variant="body" style={{ fontWeight: '700', fontSize: 14 }}>{name}</AppText>
                      <AppText variant="muted" style={{ fontSize: 11 }}>{link.athlete_detail.email}</AppText>
                      {link.notes ? <AppText variant="muted" style={{ fontSize: 11 }}>Nota: {link.notes}</AppText> : null}
                    </View>
                  </View>

                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                    <Pressable
                      onPress={() => toggleWatchlist(link)}
                      style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 8, backgroundColor: isExpanded ? `${colors.accentNeon}20` : colors.bgElevated, borderRadius: 10, borderWidth: 1, borderColor: isExpanded ? colors.accentNeon : colors.borderSubtle }}
                    >
                      <Ionicons name={isExpanded ? 'chevron-up' : 'calendar-outline'} size={14} color={isExpanded ? colors.accentNeon : colors.textSecondary} />
                      <AppText variant="caption" style={{ color: isExpanded ? colors.accentNeon : colors.textSecondary, fontWeight: '600' }}>
                        Agenda
                      </AppText>
                    </Pressable>
                    <Pressable
                      onPress={() => onRemove(link)}
                      style={{ padding: 8, backgroundColor: `${colors.danger}15`, borderRadius: 10, borderWidth: 1, borderColor: `${colors.danger}30` }}
                    >
                      <Ionicons name="trash-outline" size={16} color={colors.danger} />
                    </Pressable>
                  </View>
                </Card>

                {isExpanded && (
                  <View style={{ marginTop: -4, backgroundColor: colors.bgCard, borderRadius: 14, padding: 12, borderTopLeftRadius: 0, borderTopRightRadius: 0, borderWidth: 1, borderTopWidth: 0, borderColor: colors.borderSubtle }}>
                    {isLoadingWl ? (
                      <LoadingBlock />
                    ) : !wlData || wlData.watchlist.length === 0 ? (
                      <AppText variant="muted" style={{ textAlign: 'center', paddingVertical: 8 }}>Nenhum torneio na agenda de {name}.</AppText>
                    ) : (
                      wlData.watchlist.map((item: WatchlistItem) => {
                        const ed = item.edition_detail;
                        const userStatus = item.user_status ?? 'none';
                        const statusColor = getUserStatusColors(colors)[userStatus] ?? colors.textMuted;
                        return (
                          <Pressable
                            key={item.id}
                            onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })}
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle }}
                          >
                            <View style={{ flex: 1 }}>
                              <AppText variant="caption" style={{ fontWeight: '600', fontSize: 12 }} numberOfLines={1}>{ed.title}</AppText>
                              {ed.start_date ? (
                                <AppText variant="muted" style={{ fontSize: 10 }}>{fmtDate(ed.start_date)}</AppText>
                              ) : null}
                            </View>
                            <View style={{ backgroundColor: `${statusColor}20`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                              <AppText variant="muted" style={{ fontSize: 10, color: statusColor }}>
                                {USER_STATUS_LABELS[userStatus] ?? userStatus}
                              </AppText>
                            </View>
                            <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
                          </Pressable>
                        );
                      })
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </ScrollView>
      )}
    </Screen>
  );
}
