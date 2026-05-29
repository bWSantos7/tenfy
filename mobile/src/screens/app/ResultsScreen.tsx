import React, { useCallback, useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import Toast from 'react-native-toast-message';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, EmptyState, LoadingBlock, Screen, SectionHeader, SelectField } from '../../components/ui';
import { TournamentListSkeleton } from '../../components/Skeleton';
import { fetchTiData, listChildren, listChildProfiles, listChildWatchlist, listProfiles, listWatchlist, saveResult, syncTiData } from '../../services/data';
import { ParentChild, PlayerProfile, TiData, WatchlistItem } from '../../types';

type Props = BottomTabScreenProps<MainTabParamList, 'Results'>;
type Nav = NativeStackNavigationProp<MainStackParamList>;

const RESULT_CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Não informada' },
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

// ─── Result Entry Modal ────────────────────────────────────────────────────────
interface ResultForm {
  category_played: string;
  position: string;
  wins: string;
  losses: string;
  notes: string;
}

function ResultEntryModal({
  item,
  onClose,
  onSaved,
}: {
  item: WatchlistItem;
  onClose: () => void;
  onSaved: (updated: WatchlistItem) => void;
}) {
  const { colors } = useTheme();
  const existing = item.result;
  const [form, setForm] = useState<ResultForm>({
    category_played: existing?.category_played ?? '',
    position: existing?.position != null ? String(existing.position) : '',
    wins: existing?.wins != null ? String(existing.wins) : '',
    losses: existing?.losses != null ? String(existing.losses) : '',
    notes: existing?.notes ?? '',
  });
  const [saving, setSaving] = useState(false);

  function field(k: keyof ResultForm) {
    return (v: string) => setForm((f) => ({ ...f, [k]: v }));
  }

  async function handleSave() {
    setSaving(true);
    try {
      await saveResult(item.id, {
        category_played: form.category_played.trim() || undefined,
        position: form.position ? Number(form.position) : null,
        wins: form.wins ? Number(form.wins) : undefined,
        losses: form.losses ? Number(form.losses) : undefined,
        notes: form.notes.trim() || undefined,
      });
      const refreshed = await listWatchlist();
      const found = (refreshed as WatchlistItem[]).find((w) => w.id === item.id);
      onSaved(found ?? item);
      Toast.show({ type: 'success', text1: 'Resultado salvo!' });
      onClose();
    } catch {
      Toast.show({ type: 'error', text1: 'Erro ao salvar resultado.' });
    } finally {
      setSaving(false);
    }
  }

  const inputStyle = {
    backgroundColor: colors.bgElevated,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.textPrimary,
    fontSize: 14,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    fontFamily: 'Poppins_400Regular',
  };

  return (
    <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' }}>
      <Pressable style={{ ...StyleSheet_absoluteFillObject }} onPress={onClose} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={{ backgroundColor: colors.bgCard, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, gap: 14 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <AppText variant="section">Registrar resultado</AppText>
            <Pressable onPress={onClose} style={{ padding: 4 }}>
              <Ionicons name="close" size={22} color={colors.textMuted} />
            </Pressable>
          </View>
          <AppText variant="caption" numberOfLines={1} style={{ color: colors.textMuted }}>{item.edition_detail.title}</AppText>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1, gap: 4 }}>
              <AppText variant="caption" style={{ fontWeight: '600' }}>Vitórias</AppText>
              <TextInput
                style={inputStyle}
                value={form.wins}
                onChangeText={field('wins')}
                keyboardType="numeric"
                placeholder="0"
                placeholderTextColor={colors.textMuted}
              />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <AppText variant="caption" style={{ fontWeight: '600' }}>Derrotas</AppText>
              <TextInput
                style={inputStyle}
                value={form.losses}
                onChangeText={field('losses')}
                keyboardType="numeric"
                placeholder="0"
                placeholderTextColor={colors.textMuted}
              />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <AppText variant="caption" style={{ fontWeight: '600' }}>Posição</AppText>
              <TextInput
                style={inputStyle}
                value={form.position}
                onChangeText={field('position')}
                keyboardType="numeric"
                placeholder="—"
                placeholderTextColor={colors.textMuted}
              />
            </View>
          </View>

          <SelectField
            label="Categoria disputada"
            value={form.category_played}
            options={RESULT_CATEGORY_OPTIONS}
            onSelect={field('category_played')}
            placeholder="Selecione a categoria"
          />

          <View style={{ gap: 4 }}>
            <AppText variant="caption" style={{ fontWeight: '600' }}>Notas / observações</AppText>
            <TextInput
              style={[inputStyle, { minHeight: 72, textAlignVertical: 'top' }]}
              value={form.notes}
              onChangeText={field('notes')}
              placeholder="Descreva como foi a competição..."
              placeholderTextColor={colors.textMuted}
              multiline
            />
          </View>

          <Button title={saving ? 'Salvando...' : 'Salvar resultado'} onPress={handleSave} loading={saving} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// Workaround for StyleSheet.absoluteFillObject in inline usage
const StyleSheet_absoluteFillObject = {
  position: 'absolute' as const,
  top: 0, left: 0, right: 0, bottom: 0,
};

// ─── Result Card ──────────────────────────────────────────────────────────────
function ResultCard({
  item,
  onEdit,
  onPress,
}: {
  item: WatchlistItem;
  onEdit: () => void;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  const r = item.result;

  const positionColor = () => {
    if (!r?.position) return colors.textMuted;
    if (r.position === 1) return '#FFD700';
    if (r.position === 2) return '#C0C0C0';
    if (r.position === 3) return '#CD7F32';
    return colors.accentNeon;
  };

  const winRate = r?.wins != null && r?.losses != null && (r.wins + r.losses) > 0
    ? Math.round((r.wins / (r.wins + r.losses)) * 100)
    : null;

  return (
    <Pressable onPress={onPress} style={{ marginBottom: 12 }}>
      <View style={{ backgroundColor: colors.bgCard, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: colors.borderSubtle }}>
        <View style={{ backgroundColor: `${colors.accentNeon}10`, paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="trophy-outline" size={14} color={colors.accentNeon} />
          <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', flex: 1 }} numberOfLines={1}>
            {item.edition_detail.title}
          </AppText>
          <Pressable onPress={onEdit} style={{ padding: 4 }} hitSlop={8}>
            <Ionicons name="create-outline" size={16} color={colors.textMuted} />
          </Pressable>
        </View>

        {r ? (
          <View style={{ flexDirection: 'row', padding: 14, gap: 8 }}>
            {r.position != null ? (
              <View style={{ alignItems: 'center', backgroundColor: colors.bgBase, borderRadius: 12, padding: 12, flex: 1, borderWidth: 1, borderColor: colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 4 }}>Posição</AppText>
                <AppText variant="title" style={{ color: positionColor(), fontSize: 22 }}>
                  {r.position === 1 ? '🥇' : r.position === 2 ? '🥈' : r.position === 3 ? '🥉' : `#${r.position}`}
                </AppText>
              </View>
            ) : null}

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

            {r.category_played ? (
              <View style={{ alignItems: 'center', backgroundColor: colors.bgBase, borderRadius: 12, padding: 12, flex: 1, borderWidth: 1, borderColor: colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: colors.textMuted, marginBottom: 4 }}>Categoria</AppText>
                <AppText variant="body" style={{ fontWeight: '700', textAlign: 'center', fontSize: 13 }} numberOfLines={2}>
                  {r.category_played}
                </AppText>
              </View>
            ) : null}
          </View>
        ) : (
          <View style={{ padding: 14, alignItems: 'center' }}>
            <AppText variant="muted" style={{ fontStyle: 'italic' }}>Sem resultado registrado. Toque no lápis para adicionar.</AppText>
          </View>
        )}

        {r?.notes ? (
          <View style={{ paddingHorizontal: 14, paddingBottom: 12 }}>
            <AppText variant="muted" style={{ fontSize: 12, fontStyle: 'italic' }}>"{r.notes}"</AppText>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export function ResultsScreen(_: Props) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const navigation = useNavigation<Nav>();
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<WatchlistItem | null>(null);
  const [profileNames, setProfileNames] = useState<Record<number, string>>({});
  const [tiData, setTiData] = useState<TiData | null>(null);
  const [tiLoading, setTiLoading] = useState(false);
  const [tiSyncing, setTiSyncing] = useState(false);
  const [primaryProfileId, setPrimaryProfileId] = useState<number | null>(null);

  async function buildData(): Promise<{ allItems: WatchlistItem[]; nameMap: Record<number, string> }> {
    if (user?.role === 'parent') {
      const [children, ownProfs] = await Promise.all([
        listChildren().catch(() => [] as ParentChild[]),
        listProfiles().catch(() => [] as PlayerProfile[]),
      ]);
      const childWatchlists = await Promise.all(
        (children as ParentChild[]).map((c) => listChildWatchlist(c.child).catch(() => [] as WatchlistItem[])),
      );
      const childProfileArrays = await Promise.all(
        (children as ParentChild[]).map((c) => listChildProfiles(c.child).catch(() => [] as PlayerProfile[])),
      );
      const allItems = (children as ParentChild[]).flatMap((_, i) =>
        (childWatchlists[i] as WatchlistItem[]).filter((it) => it.user_status === 'registered_declared' || !!it.result),
      );
      const nameMap: Record<number, string> = {};
      (ownProfs as PlayerProfile[]).forEach((p) => { nameMap[p.id] = p.display_name; });
      (children as ParentChild[]).forEach((link, i) => {
        (childProfileArrays[i] as PlayerProfile[]).forEach((p) => {
          nameMap[p.id] = `${link.child_detail.full_name || link.child_detail.email} — ${p.display_name}`;
        });
      });
      return { allItems, nameMap };
    }
    const [list, profs] = await Promise.all([listWatchlist(), listProfiles().catch(() => [] as PlayerProfile[])]);
    const primary = (profs as PlayerProfile[]).find((p) => p.is_primary) ?? (profs as PlayerProfile[])[0];
    if (primary) setPrimaryProfileId(primary.id);
    return {
      allItems: (list as WatchlistItem[]).filter((it) => it.user_status === 'registered_declared' || !!it.result),
      nameMap: Object.fromEntries((profs as PlayerProfile[]).map((p) => [p.id, p.display_name])),
    };
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const { allItems, nameMap } = await buildData();
      setItems(allItems);
      setProfileNames(nameMap);
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
      const { allItems, nameMap } = await buildData();
      setItems(allItems);
      setProfileNames(nameMap);
    } catch {
      setError('Não foi possível atualizar seus resultados agora.');
    } finally {
      setRefreshing(false);
    }
  }

  useFocusEffect(useCallback(() => {
    load();
  }, []));

  // Load TI results whenever the primary profile changes
  React.useEffect(() => {
    if (!primaryProfileId || user?.role === 'parent') return;
    setTiLoading(true);
    fetchTiData(primaryProfileId)
      .then((d) => setTiData(d))
      .catch(() => {})
      .finally(() => setTiLoading(false));
  }, [primaryProfileId]);

  function onSaved(updated: WatchlistItem) {
    setItems((prev) => prev.map((i) => i.id === updated.id ? updated : i));
  }

  const totalWins   = items.reduce((sum, i) => sum + (i.result?.wins   ?? 0), 0);
  const totalLosses = items.reduce((sum, i) => sum + (i.result?.losses ?? 0), 0);
  const totalMatches = totalWins + totalLosses;

  function renderResultItem(item: WatchlistItem) {
    return (
      <ResultCard
        key={item.id}
        item={item}
        onEdit={() => setEditingItem(item)}
        onPress={() => navigation.navigate('TournamentDetail', { id: item.edition_detail.id, edition: item.edition_detail })}
      />
    );
  }

  function renderGroupedResults() {
    if (user?.role !== 'parent') return items.map(renderResultItem);

    const groups: Record<string, WatchlistItem[]> = {};
    items.forEach((item) => {
      const key = item.profile != null ? String(item.profile) : 'none';
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });

    return Object.entries(groups).map(([key, groupItems]) => {
      const profileId = key === 'none' ? null : Number(key);
      const name = profileId ? profileNames[profileId] ?? 'Dependente' : 'Sem perfil';
      return (
        <View key={key}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6, marginTop: 4 }}>
            <Ionicons name="person-outline" size={14} color={colors.accentBlue} />
            <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700' }}>{name}</AppText>
          </View>
          {groupItems.map(renderResultItem)}
        </View>
      );
    });
  }

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <SectionHeader title="Resultados" subtitle="Torneios inscritos e resultados" />

      {items.length > 0 && (
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 4 }}>
          {[
            { label: 'Inscritos', value: items.length, color: colors.accentNeon },
            { label: 'Vitórias', value: totalWins, color: colors.statusOpen },
            { label: 'Derrotas', value: totalLosses, color: colors.statusCanceled },
            { label: 'Partidas', value: totalMatches, color: colors.accentBlue },
          ].map((s) => (
            <View key={s.label} style={{ flex: 1, backgroundColor: colors.bgCard, borderRadius: 14, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="body" style={{ fontWeight: '800', fontSize: 18, color: s.color }}>{s.value}</AppText>
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
          action={<Button title="Tentar novamente" onPress={load} variant="ghost" />}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Nenhuma inscrição ainda"
          subtitle="Na Agenda, marque um torneio como 'Inscrito' para acompanhar seus resultados aqui."
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
        renderGroupedResults()
      )}

      {/* ── Resultados do Tênis Integrado ─────────────────────────────────── */}
      {user?.role !== 'parent' && (
        <>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, marginBottom: 12 }}>
            <View>
              <AppText variant="section">Jogos (Tênis Integrado)</AppText>
              <AppText variant="caption" style={{ marginTop: 2 }}>Resultados importados automaticamente</AppText>
            </View>
            {tiData?.ti_id && primaryProfileId ? (
              <Pressable
                disabled={tiSyncing}
                hitSlop={8}
                onPress={async () => {
                  setTiSyncing(true);
                  try {
                    await syncTiData(primaryProfileId);
                    const fresh = await fetchTiData(primaryProfileId);
                    setTiData(fresh);
                  } catch { /* ignore */ } finally { setTiSyncing(false); }
                }}
              >
                <Ionicons name={tiSyncing ? 'refresh' : 'refresh-outline'} size={18} color={tiSyncing ? colors.accentNeon : colors.textMuted} />
              </Pressable>
            ) : null}
          </View>

          {tiLoading ? (
            <View style={{ paddingVertical: 16, alignItems: 'center' }}>
              <AppText variant="muted">Carregando resultados...</AppText>
            </View>
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
              {tiData.results.map((r, i) => (
                <View
                  key={i}
                  style={{ backgroundColor: colors.bgCard, borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: colors.borderSubtle }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                    {/* Outcome badge */}
                    <View style={{
                      width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center',
                      backgroundColor: r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W'
                        ? `${colors.statusOpen}22` : `${colors.danger}22`,
                    }}>
                      <AppText variant="caption" style={{
                        fontWeight: '800', fontSize: 12,
                        color: r.outcome?.toUpperCase().startsWith('V') || r.outcome?.toUpperCase() === 'W'
                          ? colors.statusOpen : colors.danger,
                      }}>
                        {r.outcome ? r.outcome.slice(0, 1).toUpperCase() : '?'}
                      </AppText>
                    </View>
                    <View style={{ flex: 1, gap: 3 }}>
                      {r.tournament ? (
                        <AppText variant="caption" style={{ fontWeight: '600', fontSize: 13 }} numberOfLines={2}>{r.tournament}</AppText>
                      ) : null}
                      {r.opponent ? (
                        <AppText variant="muted" style={{ fontSize: 12 }}>vs {r.opponent}</AppText>
                      ) : null}
                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                        {r.round ? <AppText variant="muted" style={{ fontSize: 10 }}>{r.round}</AppText> : null}
                        {r.category ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.category}</AppText> : null}
                        {r.score ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.score}</AppText> : null}
                        {r.date ? <AppText variant="muted" style={{ fontSize: 10 }}>• {r.date}</AppText> : null}
                      </View>
                    </View>
                  </View>
                </View>
              ))}
              {tiData.is_stale ? (
                <AppText variant="muted" style={{ fontSize: 10, textAlign: 'center', marginTop: 4 }}>
                  Dados podem estar desatualizados. Toque em ↻ para atualizar.
                </AppText>
              ) : null}
            </>
          )}
        </>
      )}

      <Modal
        visible={!!editingItem}
        transparent
        animationType="slide"
        onRequestClose={() => setEditingItem(null)}
      >
        {editingItem ? (
          <ResultEntryModal
            item={editingItem}
            onClose={() => setEditingItem(null)}
            onSaved={(updated) => { onSaved(updated); setEditingItem(null); }}
          />
        ) : null}
      </Modal>
    </Screen>
  );
}
