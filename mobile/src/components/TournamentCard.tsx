import React, { useRef } from 'react';
import { Animated, Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { TournamentEditionList, TournamentStatus } from '../types';
import { useTheme } from '../contexts/ThemeContext';
import { AppText } from './ui';
import { STATUS_LABELS, fmtBRL, fmtDateRange } from '../utils/format';
import { haptic } from '../hooks/useHaptic';
import { hasEmailLike } from '../utils/sanitize';

function getStatusStyle(status: TournamentStatus, colors: ReturnType<typeof useTheme>['colors']) {
  switch (status) {
    case 'open':            return { color: colors.statusOpen,     icon: 'checkmark-circle' as const };
    case 'closing_soon':    return { color: colors.statusClosing,  icon: 'alarm' as const };
    case 'closed':          return { color: colors.statusClosed,   icon: 'lock-closed' as const };
    case 'draws_published': return { color: colors.statusDrawn,    icon: 'git-branch' as const };
    case 'in_progress':     return { color: colors.statusProgress, icon: 'play-circle' as const };
    case 'finished':        return { color: colors.statusFinished, icon: 'checkmark-done' as const };
    case 'canceled':        return { color: colors.statusCanceled, icon: 'close-circle' as const };
    default:                return { color: colors.textMuted,      icon: 'ellipse' as const };
  }
}

function getDaysUntil(isoDate: string | null | undefined): number | null {
  if (!isoDate) return null;
  const diff = new Date(isoDate).getTime() - Date.now();
  const days = Math.ceil(diff / 86_400_000);
  return days;
}

function DeadlineBadge({ daysUntil, colors }: { daysUntil: number; colors: any }) {
  if (daysUntil < 0) return null;
  const urgent = daysUntil <= 2;
  const warning = daysUntil <= 7;
  const color = urgent ? colors.statusCanceled : warning ? colors.statusClosing : colors.textMuted;
  const label = daysUntil === 0 ? 'Fecha hoje' : daysUntil === 1 ? 'Fecha amanhã' : `Fecha em ${daysUntil}d`;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: `${color}18`, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: `${color}33` }}>
      <Ionicons name={urgent ? 'alarm' : 'time-outline'} size={11} color={color} />
      <AppText variant="caption" style={{ color, fontWeight: '700', fontSize: 11 }}>{label}</AppText>
    </View>
  );
}

export function TournamentCard({
  edition,
  showEligibility = false,
  onPress,
}: {
  edition: TournamentEditionList;
  showEligibility?: boolean;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  const scale = useRef(new Animated.Value(1)).current;
  const status = edition.dynamic_status || edition.status;
  const { color: statusColor, icon: statusIcon } = getStatusStyle(status, colors);
  const safeCity = (edition.venue_city && !hasEmailLike(edition.venue_city)) ? edition.venue_city : '';
  const location = [safeCity, edition.venue_state].filter(Boolean).join(' · ');
  const daysUntil = getDaysUntil(edition.entry_close_at);
  const showDeadline = daysUntil !== null && daysUntil >= 0 && ['open', 'closing_soon'].includes(status);

  function handlePressIn() {
    Animated.spring(scale, { toValue: 0.97, useNativeDriver: true, speed: 50 }).start();
  }
  function handlePressOut() {
    Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 30 }).start();
  }
  function handlePress() {
    haptic.light();
    onPress?.();
  }

  return (
    <Pressable
      onPress={handlePress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      style={{ marginBottom: 14 }}
    >
      <Animated.View
        style={[
          styles.card,
          {
            backgroundColor: colors.bgCard,
            borderColor: colors.borderSubtle,
            transform: [{ scale }],
          },
        ]}
      >
        {/* Top row: org + status badge */}
        <View style={styles.topRow}>
          <View style={{ flex: 1 }}>
            <View style={styles.orgRow}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: statusColor, flexShrink: 0 }} />
              <AppText variant="caption" numberOfLines={1} style={{ color: colors.accentBlue, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, flexShrink: 1 }}>
                {edition.organization_short || edition.organization_name}
              </AppText>
            </View>
            <AppText variant="body" style={styles.title} numberOfLines={2}>{edition.title}</AppText>
          </View>

          {/* Status badge */}
          <View style={[styles.statusBadge, { backgroundColor: `${statusColor}18`, borderColor: `${statusColor}33` }]}>
            <Ionicons name={statusIcon} size={12} color={statusColor} />
            <AppText variant="caption" style={{ color: statusColor, fontWeight: '700', fontSize: 11 }}>
              {STATUS_LABELS[status] || status}
            </AppText>
          </View>
        </View>

        {/* Info row */}
        <View style={styles.infoRow}>
          {edition.start_date ? (
            <View style={styles.infoItem}>
              <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption" style={{ color: colors.textSecondary }}>{fmtDateRange(edition.start_date, edition.end_date)}</AppText>
            </View>
          ) : (
            <View style={styles.infoItem}>
              <Ionicons name="calendar-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption" style={{ color: colors.textMuted, fontStyle: 'italic' }}>Data a confirmar</AppText>
            </View>
          )}
          {location ? (
            <View style={styles.infoItem}>
              <Ionicons name="location-outline" size={13} color={colors.textMuted} />
              <AppText variant="caption" style={{ color: colors.textSecondary }}>{location}</AppText>
            </View>
          ) : null}
        </View>

        {/* Bottom row: deadline badge + price + eligibility */}
        <View style={styles.bottomRow}>
          {showDeadline && daysUntil !== null ? (
            <DeadlineBadge daysUntil={daysUntil} colors={colors} />
          ) : null}

          {edition.base_price_brl != null ? (
            <View style={[styles.priceBadge, { backgroundColor: colors.bgElevated, borderColor: colors.borderSubtle }]}>
              <AppText variant="caption" style={{ color: colors.textSecondary, fontWeight: '600', fontSize: 11 }}>
                {fmtBRL(edition.base_price_brl)}
              </AppText>
            </View>
          ) : null}

          {edition.has_online_entry ? (
            <View style={[styles.eligBadge, { backgroundColor: `${colors.accentBlue}12`, borderColor: `${colors.accentBlue}30` }]}>
              <Ionicons name="link-outline" size={12} color={colors.accentBlue} />
              <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700', fontSize: 11 }}>
                Inscrição Online
              </AppText>
            </View>
          ) : null}

          {showEligibility && (edition.eligibility?.compatible_count ?? 0) > 0 ? (
            <View style={[styles.eligBadge, { backgroundColor: `${colors.accentNeon}12`, borderColor: `${colors.accentNeon}30` }]}>
              <Ionicons name="checkmark-circle" size={12} color={colors.accentNeon} />
              <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700', fontSize: 11 }}>
                {edition.eligibility!.compatible_count} compat.
              </AppText>
            </View>
          ) : null}

          {showEligibility && edition.eligibility?.entry_model === 'acceptance_list' ? (
            <View style={[styles.eligBadge, { backgroundColor: '#f59e0b12', borderColor: '#f59e0b30' }]}>
              <Ionicons name="information-circle-outline" size={12} color="#f59e0b" />
              <AppText variant="caption" style={{ color: '#f59e0b', fontWeight: '700', fontSize: 11 }}>
                Sujeito à aceitação
              </AppText>
            </View>
          ) : null}
        </View>
        {showEligibility && edition.eligibility?.entry_model === 'acceptance_list' && edition.eligibility?.distance_message ? (
          <AppText variant="caption" style={{ color: colors.textMuted, fontSize: 10, marginTop: -4 }}>
            {edition.eligibility.distance_message}
          </AppText>
        ) : null}
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    gap: 10,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  orgRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 4,
    overflow: 'hidden',
  },
  title: {
    fontWeight: '700',
    fontSize: 15,
    lineHeight: 20,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignSelf: 'flex-start',
    flexShrink: 0,
  },
  infoRow: {
    gap: 5,
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  priceBadge: {
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
  },
  eligBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
  },
});
