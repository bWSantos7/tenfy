import React, { useCallback, useRef, useState } from 'react';
import { Image, Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { MainStackParamList, MainTabParamList } from '../../navigation/types';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { AppText, Button, EmptyState, LoadingBlock, Screen, SectionHeader } from '../../components/ui';
import { haptic } from '../../hooks/useHaptic';
import { TournamentCard } from '../../components/TournamentCard';
import { listProfiles, unreadAlerts } from '../../services/data';
import { closingSoon, compatibleForProfile, listEditions } from '../../services/tournaments';
import { PlayerProfile, TournamentEditionList } from '../../types';
import { pickBestProfile } from '../../utils/profile';

type Props = BottomTabScreenProps<MainTabParamList, 'Home'>;
type StackNav = NativeStackNavigationProp<MainStackParamList>;

export function HomeScreen(_: Props) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const navigation = useNavigation<StackNav>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [compat, setCompat] = useState<TournamentEditionList[]>([]);
  const [closing, setClosing] = useState<TournamentEditionList[]>([]);
  const [recent, setRecent] = useState<TournamentEditionList[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const hasLoadedRef = useRef(false);

  const loadData = useCallback(async (active = { current: true }) => {
    setError(null);
    try {
      const [profiles, closingData, recentData, alerts] = await Promise.all([
        listProfiles(),
        closingSoon(14),
        listEditions({ page_size: 8, ordering: '-created_at' }),
        unreadAlerts().catch(() => []),
      ]);
      if (!active.current) return;
      const primary = pickBestProfile(profiles as PlayerProfile[]);
      setHasProfile((profiles as PlayerProfile[]).length > 0);
      setProfile(primary);
      setClosing((closingData as TournamentEditionList[]).slice(0, 6));
      const HIDDEN = ['finished', 'canceled'];
      setRecent(((recentData.results || []) as TournamentEditionList[]).filter((ed) => !HIDDEN.includes(ed.dynamic_status || ed.status)).slice(0, 6));
      setUnreadCount((alerts || []).length);
      if (primary) {
        const compatData = await compatibleForProfile(primary.id, { page_size: 8 }).catch(() => ({ results: [] as TournamentEditionList[] }));
        if (!active.current) return;
        setCompat((compatData.results || []).slice(0, 8));
      }
      hasLoadedRef.current = true;
    } catch {
      if (active.current) setError('Não foi possível carregar os dados. Verifique sua conexão.');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      const active = { current: true };
      if (!hasLoadedRef.current) setLoading(true);
      loadData(active).finally(() => { if (active.current) setLoading(false); });
      return () => { active.current = false; };
    }, [loadData]),
  );

  async function onRefresh() {
    setRefreshing(true);
    hasLoadedRef.current = false;
    await loadData();
    setRefreshing(false);
  }

  function handleRetry() {
    setError(null);
    setLoading(true);
    hasLoadedRef.current = false;
    loadData().finally(() => setLoading(false));
  }

  if (loading) return <Screen><LoadingBlock /></Screen>;

  if (error) return (
    <Screen>
      <EmptyState
        icon="wifi-outline"
        title="Erro ao carregar"
        subtitle="Não foi possível carregar os dados. Verifique sua conexão."
        action={<Button title="Tentar novamente" onPress={handleRetry} />}
      />
    </Screen>
  );

  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
          {user?.avatar
            ? <Image source={{ uri: user.avatar }} style={{ width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.borderSubtle }} />
            : <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.accentNeon}20`, borderWidth: 1, borderColor: `${colors.accentNeon}40`, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="person" size={20} color={colors.accentNeon} />
              </View>
          }
          <View style={{ flex: 1 }}>
            <AppText variant="caption" style={{ color: colors.textMuted }}>Olá,</AppText>
            <AppText variant="body" style={{ fontWeight: '700', fontSize: 16 }}>{user?.full_name || profile?.display_name || user?.email?.split('@')[0] || 'Jogador'}</AppText>
            {profile ? <AppText variant="caption" style={{ marginTop: 2 }}>{profile.tennis_class ? `Classe ${profile.tennis_class}` : ''}{profile.sporting_age ? ` • ${profile.sporting_age} anos esportivos` : ''}{profile.home_state ? ` • ${profile.home_state}` : ''}</AppText> : null}
          </View>
        </View>
        <Pressable onPress={() => navigation.navigate('Tabs', { screen: 'Alerts' } as never)} style={{ padding: 8 }}>
          <View>
            <Ionicons name="notifications-outline" size={22} color={colors.textPrimary} />
            {unreadCount > 0 ? <View style={{ position: 'absolute', right: -4, top: -4, width: 18, height: 18, borderRadius: 9, backgroundColor: colors.accentNeon, alignItems: 'center', justifyContent: 'center' }}><AppText variant="caption" style={{ color: colors.bgBase, fontWeight: '700', fontSize: 10 }}>{unreadCount > 9 ? '9+' : unreadCount}</AppText></View> : null}
          </View>
        </Pressable>
      </View>

      {!hasProfile && user?.role !== 'parent' ? (
        <View style={{ borderWidth: 1, borderColor: `${colors.accentNeon}55`, backgroundColor: `${colors.accentNeon}10`, borderRadius: 20, padding: 16, flexDirection: 'row', gap: 12 }}>
          <Ionicons name="sparkles-outline" size={20} color={colors.accentNeon} />
          <View style={{ flex: 1 }}>
            <AppText variant="body" style={{ fontWeight: '600' }}>Complete seu perfil</AppText>
            <AppText variant="muted" style={{ marginTop: 4 }}>Informe sua categoria, idade e localização para ver torneios compatíveis com você.</AppText>
          </View>
          <Button title="Configurar" onPress={() => navigation.navigate('Onboarding')} />
        </View>
      ) : null}

      {profile ? (
        <View>
          <SectionHeader
            title="Compatíveis com você"
            subtitle="Baseado no seu perfil e categoria"
            action={
              <Pressable onPress={() => { haptic.select(); navigation.navigate('Tabs', { screen: 'Tournaments' } as never); }}>
                <AppText variant="caption" style={{ color: colors.accentNeon, fontWeight: '700' }}>Ver todos</AppText>
              </Pressable>
            }
          />
          {compat.length === 0
            ? <EmptyState title="Nenhum torneio compatível com o seu perfil." subtitle="Revise cidade, raio de viagem, classe e categoria no perfil." icon="trophy-outline" />
            : compat.map((ed) => <TournamentCard key={ed.id} edition={ed} showEligibility onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })} />)
          }
        </View>
      ) : null}

      <View>
        <SectionHeader
          title="Inscrições fechando"
          subtitle="Próximos 14 dias"
          action={
            <Pressable onPress={() => { haptic.select(); navigation.navigate('Tabs', { screen: 'Tournaments' } as never); }}>
              <AppText variant="caption" style={{ color: colors.statusClosing, fontWeight: '700' }}>Ver todos</AppText>
            </Pressable>
          }
        />
        {closing.length === 0
          ? <EmptyState title="Nenhum prazo se aproximando." subtitle="Quando torneios estiverem com inscrições abrindo, aparecerão aqui." icon="alarm-outline" />
          : closing.map((ed) => <TournamentCard key={ed.id} edition={ed} onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })} />)
        }
      </View>

      <View>
        <SectionHeader
          title="Recentemente adicionados"
          subtitle="Últimos torneios agregados"
          action={
            <Pressable onPress={() => { haptic.select(); navigation.navigate('Tabs', { screen: 'Tournaments' } as never); }}>
              <AppText variant="caption" style={{ color: colors.accentBlue, fontWeight: '700' }}>Ver todos</AppText>
            </Pressable>
          }
        />
        {recent.length === 0
          ? <EmptyState title="Nenhum torneio na base ainda." subtitle="As ingestões acontecem automaticamente a cada hora." icon="refresh-outline" />
          : recent.map((ed) => <TournamentCard key={ed.id} edition={ed} onPress={() => navigation.navigate('TournamentDetail', { id: ed.id, edition: ed })} />)
        }
      </View>

      {/* Circuit Explorer — spec requirement: "Explorar por circuito" */}
      <View>
        <SectionHeader title="Explorar por circuito" subtitle="Selecione um circuito para ver torneios" />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {CIRCUITS.map((c) => (
            <Pressable
              key={c.key}
              onPress={() => navigation.navigate('Tabs', { screen: 'Tournaments', params: { circuit: c.key } } as never)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 20, backgroundColor: `${c.color}18`, borderWidth: 1, borderColor: `${c.color}44` }}
            >
              <AppText variant="caption" style={{ color: c.color, fontWeight: '700', fontSize: 13 }}>{c.label}</AppText>
            </Pressable>
          ))}
        </View>
      </View>
    </Screen>
  );
}

const CIRCUITS = [
  { key: 'FPT',   label: 'FPT',   color: '#39ff14' },
  { key: 'CBT',   label: 'CBT',   color: '#3b82f6' },
  { key: 'COSAT', label: 'COSAT', color: '#f59e0b' },
  { key: 'ITF',   label: 'ITF',   color: '#8b5cf6' },
  { key: 'UTR',   label: 'UTR',   color: '#ef4444' },
  { key: 'FCT',   label: 'FCT',   color: '#06b6d4' },
];
