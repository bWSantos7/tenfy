import React, { useEffect, useState } from 'react';
import { Alert, Linking, Modal, Pressable, ScrollView, Share, View } from 'react-native';
import Toast from 'react-native-toast-message';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { MainStackParamList } from '../../navigation/types';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, Card, EmptyState, Input, LoadingBlock, Screen, SectionHeader, SelectField } from '../../components/ui';
import {
  EditionEligibility,
  TournamentChangeEvent,
  TournamentEditionDetail,
  TournamentRegistration,
} from '../../types';
import { getEdition, evaluateEdition, editionHistory } from '../../services/tournaments';
import { listProfiles, listWatchlist, toggleWatchlist } from '../../services/data';
import { myRegistrations, registerForEdition, withdrawRegistration } from '../../services/registrations';
import { pickBestProfile } from '../../utils/profile';
import { fmtBRL, fmtDate, fmtDateMaybeTime, fmtDateRange, formatChangeEventDetails, formatChangeEventTitle, translateReason, STATUS_LABELS, SURFACE_LABELS } from '../../utils/format';
import { extractApiError } from '../../services/api';

type Props = NativeStackScreenProps<MainStackParamList, 'TournamentDetail'>;

function getStatusColors(colors: ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors']): Record<string, string> {
  return {
    open: colors.statusOpen,
    closing_soon: colors.statusClosing,
    closed: colors.danger,
    registration_open: colors.statusOpen,
    registration_closed: colors.danger,
    in_progress: colors.accentBlue,
    finished: colors.statusFinished,
    canceled: colors.danger,
    draw_published: colors.statusProgress,
  };
}

function getRegStatusConfig(colors: ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors']): Record<string, { color: string; icon: string }> {
  return {
    confirmed: { color: colors.statusOpen, icon: 'checkmark-circle' },
    waiting_list: { color: colors.statusClosing, icon: 'time' },
    pending_payment: { color: colors.accentBlue, icon: 'card' },
    withdrawn: { color: colors.statusClosed, icon: 'close-circle' },
  };
}

export function TournamentDetailScreen({ route, navigation }: Props) {
  const { colors } = useTheme();
  const id = route.params.id;
  const preloaded = route.params.edition;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<TournamentEditionDetail | null>(null);
  const [eligibility, setEligibility] = useState<EditionEligibility | null>(null);
  const [history, setHistory] = useState<TournamentChangeEvent[]>([]);
  const [watching, setWatching] = useState(false);
  const [togglingWatch, setTogglingWatch] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [myReg, setMyReg] = useState<TournamentRegistration | null>(null);
  const [showRegModal, setShowRegModal] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await getEdition(id);
      setDetail(d);
      const [profiles, hist, regs, watchlist] = await Promise.all([
        listProfiles().catch(() => []),
        editionHistory(id).catch(() => [] as TournamentChangeEvent[]),
        myRegistrations().catch(() => [] as TournamentRegistration[]),
        listWatchlist().catch(() => []),
      ]);
      setHistory((hist ?? []) as TournamentChangeEvent[]);
      const regList = (regs ?? []) as TournamentRegistration[];
      const existing = regList.find((r) => r.edition_id === id && !r.is_withdrawn);
      setMyReg(existing ?? null);
      const wlArray = Array.isArray(watchlist) ? watchlist : ((watchlist as { results?: unknown[] }).results ?? []);
      setWatching(wlArray.some((w) => {
        const item = w as { edition?: number; edition_id?: number };
        return item.edition === id || item.edition_id === id;
      }));
      const primary = pickBestProfile(profiles as Parameters<typeof pickBestProfile>[0]);
      if (primary) {
        const elig = await evaluateEdition(id, primary.id).catch(() => null);
        setEligibility(elig as EditionEligibility | null);
      }
    } catch (err) {
      setError(extractApiError(err));
      Toast.show({ type: 'error', text1: 'Erro ao carregar torneio', text2: extractApiError(err) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [id]);

  async function onShare() {
    if (!detail) return;
    try {
      await Share.share({
        title: detail.title,
        message: `${detail.title}${detail.official_source_url ? `\n${detail.official_source_url}` : ''}`,
        url: detail.official_source_url || undefined,
      });
    } catch {}
  }

  async function onToggleWatch() {
    if (!detail) return;
    setTogglingWatch(true);
    try {
      const profiles = await listProfiles().catch(() => []);
      const primary = pickBestProfile(profiles as Parameters<typeof pickBestProfile>[0]);
      const result = await toggleWatchlist(id, primary?.id);
      setWatching(result.watching);
      Toast.show({ type: 'success', text1: result.watching ? 'Adicionado à agenda' : 'Removido da agenda' });
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Não foi possível atualizar a agenda', text2: extractApiError(err) });
    } finally {
      setTogglingWatch(false);
    }
  }

  function onWithdraw() {
    if (!myReg) return;
    Alert.alert(
      'Cancelar inscrição',
      'Tem certeza que deseja cancelar sua inscrição neste torneio?',
      [
        { text: 'Não, manter', style: 'cancel' },
        {
          text: 'Sim, cancelar',
          style: 'destructive',
          onPress: async () => {
            try {
              await withdrawRegistration(myReg.id);
              setMyReg(null);
              Toast.show({ type: 'success', text1: 'Inscrição cancelada.' });
            } catch (err) {
              Toast.show({ type: 'error', text1: 'Erro ao cancelar', text2: extractApiError(err) });
            }
          },
        },
      ],
    );
  }

  const STATUS_COLORS = getStatusColors(colors);
  const REG_STATUS_CONFIG = getRegStatusConfig(colors);
  const statusColor = detail ? (STATUS_COLORS[detail.status] ?? colors.textMuted) : colors.textMuted;
  const statusLabel = detail ? (STATUS_LABELS[detail.status] ?? detail.status) : '';

  if (loading) {
    return (
      <Screen scroll={false}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
          </Pressable>
          <AppText variant="body" style={{ fontWeight: '600' }}>{preloaded?.title ?? 'Carregando...'}</AppText>
        </View>
        <LoadingBlock />
      </Screen>
    );
  }

  if (error || !detail) {
    return (
      <Screen scroll={false}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
          </Pressable>
          <AppText variant="body" style={{ fontWeight: '600' }}>Erro</AppText>
        </View>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', gap: 16 }}>
          <Ionicons name="alert-circle-outline" size={48} color={colors.danger} />
          <AppText variant="body" style={{ textAlign: 'center', fontWeight: '600' }}>Não foi possível carregar o torneio</AppText>
          <AppText variant="muted" style={{ textAlign: 'center' }}>{error ?? 'Torneio não encontrado.'}</AppText>
          <Button title="Tentar novamente" onPress={load} />
          <Button title="Voltar" variant="ghost" onPress={() => navigation.goBack()} />
        </View>
      </Screen>
    );
  }

  const visibleCategories = showAllCategories ? detail.categories : detail.categories.slice(0, 3);
  const regSC = myReg ? (REG_STATUS_CONFIG[myReg.registration_status] ?? REG_STATUS_CONFIG.pending_payment) : null;

  return (
    <Screen>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <Pressable onPress={() => navigation.goBack()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <Pressable onPress={onShare} style={{ padding: 4 }}>
          <Ionicons name="share-outline" size={22} color={colors.textPrimary} />
        </Pressable>
      </View>

      {/* Main info card */}
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
          <AppText variant="muted" style={{ fontSize: 12 }}>{detail.organization_short || detail.organization_name}</AppText>
          <View style={{ backgroundColor: `${statusColor}20`, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 }}>
            <AppText variant="muted" style={{ fontSize: 11, color: statusColor, fontWeight: '600' }}>{statusLabel}</AppText>
          </View>
        </View>

        <AppText variant="title" style={{ marginBottom: 12 }}>{detail.title}</AppText>

        <View style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="calendar-outline" size={14} color={colors.textMuted} />
            <AppText variant="caption">Período do torneio: {fmtDateRange(detail.start_date, detail.end_date)}</AppText>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="create-outline" size={14} color={colors.textMuted} />
            {(detail.entry_open_at || detail.entry_close_at) ? (
              <AppText variant="caption">Inscrições: {fmtDateRange(detail.entry_open_at, detail.entry_close_at)}</AppText>
            ) : (
              <AppText variant="caption" style={{ color: colors.textMuted, fontStyle: 'italic' }}>Inscrição não informada</AppText>
            )}
          </View>
          {detail.entry_close_at && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="time-outline" size={14} color={colors.textMuted} />
              <AppText variant="caption">Prazo final de inscrição: {fmtDateMaybeTime(detail.entry_close_at)}</AppText>
            </View>
          )}
          {(detail.venue_city || detail.venue_state) && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="location-outline" size={14} color={colors.textMuted} />
              <AppText variant="caption">Local: {[detail.venue_city, detail.venue_state].filter(Boolean).join(' / ')}</AppText>
            </View>
          )}
          {detail.surface && detail.surface !== 'unknown' && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="tennisball-outline" size={14} color={colors.textMuted} />
              <AppText variant="caption">Superfície: {SURFACE_LABELS[detail.surface] ?? detail.surface}</AppText>
            </View>
          )}
          {detail.base_price_brl != null && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="cash-outline" size={14} color={colors.textMuted} />
              <AppText variant="caption">Taxa de inscrição: {fmtBRL(detail.base_price_brl)}</AppText>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 14 }}>
          <Button
            title={watching ? 'Na agenda' : 'Adicionar à agenda'}
            onPress={onToggleWatch}
            loading={togglingWatch}
          />
          {detail.official_source_url ? (
            <Button
              title="Página oficial"
              variant="secondary"
              onPress={() => Linking.openURL(detail.official_source_url)}
            />
          ) : null}
        </View>
        <Button
          title="Ver lista de inscritos"
          variant="secondary"
          onPress={() => navigation.navigate('RegistrationList', { editionId: id, editionTitle: detail.title })}
        />
      </Card>

      {/* My Registration status */}
      {myReg && regSC ? (
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Ionicons name={regSC.icon as any} size={20} color={regSC.color} />
            <AppText variant="body" style={{ fontWeight: '700', color: regSC.color }}>
              {myReg.registration_status_label}
            </AppText>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {myReg.slot_position != null ? (
              <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: colors.textMuted }}>Posição</AppText>
                <AppText variant="body" style={{ fontWeight: '700', fontSize: 24, color: myReg.in_draw ? colors.accentNeon : colors.textPrimary }}>
                  #{myReg.slot_position}
                </AppText>
                {myReg.max_participants ? (
                  <AppText variant="caption" style={{ color: myReg.in_draw ? colors.accentNeon : colors.danger, textAlign: 'center' }}>
                    {myReg.in_draw ? 'Na chave' : `Fora (limite ${myReg.max_participants})`}
                  </AppText>
                ) : null}
              </View>
            ) : null}
            <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
              <AppText variant="caption" style={{ color: colors.textMuted }}>Pagamento</AppText>
              <Ionicons
                name={myReg.payment_status === 'paid' || myReg.payment_status === 'waived' ? 'checkmark-circle' : 'time'}
                size={22}
                color={myReg.payment_status === 'paid' || myReg.payment_status === 'waived' ? colors.accentNeon : colors.statusClosing}
                style={{ marginVertical: 2 }}
              />
              <AppText variant="caption" style={{ color: myReg.payment_status === 'paid' || myReg.payment_status === 'waived' ? colors.accentNeon : colors.statusClosing, fontWeight: '600' }}>
                {myReg.payment_status_label}
              </AppText>
            </View>
            {myReg.category_text ? (
              <View style={{ flex: 1, backgroundColor: colors.bgBase, borderRadius: 12, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.borderSubtle }}>
                <AppText variant="caption" style={{ color: colors.textMuted }}>Categoria</AppText>
                <AppText variant="caption" style={{ fontWeight: '600', textAlign: 'center', marginTop: 4 }}>{myReg.category_text}</AppText>
              </View>
            ) : null}
          </View>
          <Button title="Cancelar minha inscrição" variant="danger" onPress={onWithdraw} style={{ marginTop: 4 }} />
        </Card>
      ) : (
        /* Register button */
        <Button
          title="Inscrever-se neste torneio"
          onPress={() => setShowRegModal(true)}
        />
      )}

      {/* Eligibility */}
      {eligibility && (
        <View>
          <SectionHeader title="Elegibilidade" subtitle="Baseado no seu perfil principal" />
          {eligibility.categories?.map((item: any) => {
            const status: string = item.result?.status ?? 'unknown';
            const isCompatible = status === 'compatible';
            const isUnknown = status === 'unknown';
            const iconName = isCompatible ? 'checkmark-circle' : isUnknown ? 'help-circle' : 'close-circle';
            const iconColor = isCompatible ? colors.accentNeon : isUnknown ? colors.statusClosing : colors.danger;
            return (
              <Card key={item.tournament_category_id} style={{ marginBottom: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Ionicons name={iconName} size={16} color={iconColor} />
                  <AppText variant="body" style={{ fontWeight: '700', flex: 1 }}>{item.source_text}</AppText>
                  {isUnknown && (
                    <View style={{ backgroundColor: `${colors.statusClosing}22`, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
                      <AppText variant="caption" style={{ color: colors.statusClosing, fontSize: 10, fontWeight: '600' }}>Indeterminado</AppText>
                    </View>
                  )}
                </View>
                {item.result?.reasons?.map((reason: string) => (
                  <AppText key={reason} variant="muted" style={{ marginLeft: 24 }}>• {translateReason(reason)}</AppText>
                ))}
                {isUnknown && !item.result?.reasons?.length ? (
                  <AppText variant="muted" style={{ marginLeft: 24, color: colors.statusClosing }}>• Regra oficial não encontrada para esta categoria</AppText>
                ) : null}
                {item.result?.ranking_check && item.result.ranking_check !== 'not_applicable' ? (
                  <AppText
                    variant="muted"
                    style={{
                      marginLeft: 24,
                      color: item.result.ranking_check === 'within_cutoff'
                        ? colors.accentNeon
                        : item.result.ranking_check === 'beyond_cutoff'
                        ? colors.statusClosing
                        : colors.textMuted,
                    }}
                  >
                    {item.result.ranking_check === 'within_cutoff' && '✓ Ranking dentro do corte estimado.'}
                    {item.result.ranking_check === 'beyond_cutoff' && '⚠ Ranking acima do corte estimado — vaga incerta. Confirme na fonte oficial.'}
                    {item.result.ranking_check === 'unknown' && (item.result.ranking_note || 'Corte de ranking não estimado.')}
                  </AppText>
                ) : null}
              </Card>
            );
          })}
        </View>
      )}

      {/* Categories */}
      <SectionHeader title="Categorias" />
      {detail.categories.length === 0 ? (
        <EmptyState title="Nenhuma categoria encontrada." />
      ) : (
        <View style={{ gap: 4 }}>
          {visibleCategories.map((c) => (
            <Card key={c.id}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <AppText variant="body" style={{ fontWeight: '700', flex: 1 }}>{c.source_category_text}</AppText>
                {c.max_participants ? (
                  <View style={{ backgroundColor: `${colors.accentBlue}22`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                    <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '600' }}>{c.max_participants} vagas</AppText>
                  </View>
                ) : null}
              </View>
              {c.price_brl != null && <AppText variant="caption">Valor: {fmtBRL(c.price_brl)}</AppText>}
              {c.notes ? <AppText variant="muted">{c.notes}</AppText> : null}
            </Card>
          ))}
          {detail.categories.length > 3 && (
            <Pressable onPress={() => setShowAllCategories(!showAllCategories)} style={{ alignItems: 'center', paddingVertical: 8 }}>
              <AppText variant="caption" style={{ color: colors.accentNeon }}>
                {showAllCategories ? 'Ver menos' : `Ver mais ${detail.categories.length - 3} categorias`}
              </AppText>
            </Pressable>
          )}
        </View>
      )}

      {/* Links */}
      {detail.links?.length > 0 && (
        <View>
          <SectionHeader title="Links" />
          <View style={{ gap: 4 }}>
            {detail.links.map((link) => (
              <Card key={link.id}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <AppText variant="body" style={{ fontWeight: '600' }}>{link.label || link.link_type}</AppText>
                  <Pressable onPress={() => Linking.openURL(link.url)}>
                    <Ionicons name="open-outline" size={18} color={colors.accentNeon} />
                  </Pressable>
                </View>
              </Card>
            ))}
          </View>
        </View>
      )}

      {/* History */}
      {history.length > 0 && (
        <View>
          <SectionHeader title="Histórico de alterações" />
          <View style={{ gap: 4 }}>
            {history.slice(0, 5).map((event: any) => (
              <Card key={event.id}>
                <AppText variant="body" style={{ fontWeight: '700' }}>{formatChangeEventTitle(event.event_type)}</AppText>
                {formatChangeEventDetails(event).map((line) => (
                  <AppText key={line} variant="muted">• {line}</AppText>
                ))}
              </Card>
            ))}
          </View>
        </View>
      )}

      {/* Registration Modal */}
      <RegistrationModal
        visible={showRegModal}
        onClose={() => setShowRegModal(false)}
        detail={detail}
        colors={colors}
        onSuccess={(reg) => { setMyReg(reg); setShowRegModal(false); }}
      />
    </Screen>
  );
}

function RegistrationModal({ visible, onClose, detail, colors, onSuccess }: {
  visible: boolean;
  onClose: () => void;
  detail: TournamentEditionDetail;
  colors: ReturnType<typeof import('../../contexts/ThemeContext').useTheme>['colors'];
  onSuccess: (reg: TournamentRegistration) => void;
}) {
  const [categoryId, setCategoryId] = useState<string>('');
  const [rankingPosition, setRankingPosition] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const categoryOptions = detail.categories.map((c) => ({
    value: String(c.id),
    label: c.source_category_text,
  }));

  async function submit() {
    setSubmitting(true);
    try {
      const reg = await registerForEdition({
        edition: detail.id,
        category: categoryId ? Number(categoryId) : null,
        ranking_position: rankingPosition ? Number(rankingPosition) : null,
      });
      Toast.show({ type: 'success', text1: 'Inscrição realizada!', text2: reg.registration_status_label });
      onSuccess(reg);
    } catch (err) {
      Toast.show({ type: 'error', text1: 'Erro ao se inscrever', text2: extractApiError(err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, justifyContent: 'flex-end' }}>
        <Pressable style={{ ...require('react-native').StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' }} onPress={onClose} />
        <ScrollView
          keyboardShouldPersistTaps="handled"
          style={{ maxHeight: '88%', backgroundColor: colors.bgCard, borderTopLeftRadius: 24, borderTopRightRadius: 24 }}
          contentContainerStyle={{ padding: 20, paddingBottom: 20, gap: 16 }}
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <AppText variant="section">Inscrever-se</AppText>
            <Pressable onPress={onClose} style={{ padding: 4 }}>
              <Ionicons name="close" size={22} color={colors.textMuted} />
            </Pressable>
          </View>
          <AppText variant="muted" numberOfLines={2}>{detail.title}</AppText>

          {categoryOptions.length > 0 ? (
            <SelectField
              label="Categoria"
              value={categoryId}
              options={[{ value: '', label: 'Sem categoria específica' }, ...categoryOptions]}
              onSelect={setCategoryId}
              placeholder="Selecione a categoria"
            />
          ) : null}

          <Input
            label="Posição no ranking (opcional)"
            value={rankingPosition}
            onChangeText={(v) => setRankingPosition(v.replace(/\D/g, ''))}
            keyboardType="number-pad"
            placeholder="Ex: 15 (deixe em branco se não souber)"
          />

          <AppText variant="muted" style={{ fontSize: 11 }}>
            A confirmação da vaga depende do pagamento da inscrição. Você receberá a posição na lista após se inscrever.
          </AppText>

          <Button title="Confirmar inscrição" onPress={submit} loading={submitting} />
          <Button title="Cancelar" variant="ghost" onPress={onClose} />
        </ScrollView>
      </View>
    </Modal>
  );
}
