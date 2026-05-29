import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { MainTabParamList } from './types';
import { HomeScreen } from '../screens/app/HomeScreen';
import { TournamentsScreen } from '../screens/app/TournamentsScreen';
import { WatchlistScreen } from '../screens/app/WatchlistScreen';
import { ResultsScreen } from '../screens/app/ResultsScreen';
import { AlertsScreen } from '../screens/app/AlertsScreen';
import { PlayerProfileScreen } from '../screens/app/PlayerProfileScreen';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../contexts/ThemeContext';

const Tab = createBottomTabNavigator<MainTabParamList>();

const icons: Record<keyof MainTabParamList, any> = {
  Home:        'home-outline',
  Tournaments: 'calendar-outline',
  Watchlist:   'star-outline',
  Results:     'ribbon-outline',
  Alerts:      'notifications-outline',
  Profile:     'person-outline',
};

export function MainTabs() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Tab.Navigator screenOptions={({ route }) => ({
      headerShown: false,
      tabBarHideOnKeyboard: true,
      sceneContainerStyle: { backgroundColor: colors.bgBase },
      tabBarStyle: {
        backgroundColor: colors.bgBase,
        borderTopWidth: 1,
        borderTopColor: colors.borderSubtle,
        elevation: 0,
        height: 48 + insets.bottom,
        paddingTop: 2,
        paddingBottom: insets.bottom,
      },
      tabBarActiveTintColor: colors.accentNeon,
      tabBarInactiveTintColor: colors.textMuted,
      tabBarLabelStyle: { fontSize: 10, fontWeight: '700', marginTop: 1 },
      tabBarIcon: ({ color, size, focused }) => (
        <Ionicons
          name={focused ? icons[route.name].replace('-outline', '') : icons[route.name]}
          color={color}
          size={focused ? size + 1 : size}
        />
      ),
    })}>
      <Tab.Screen name="Home"        component={HomeScreen}        options={{ title: 'Início' }} />
      <Tab.Screen name="Tournaments" component={TournamentsScreen} options={{ title: 'Torneios' }} />
      <Tab.Screen name="Watchlist"   component={WatchlistScreen}   options={{ title: 'Agenda' }} />
      <Tab.Screen name="Results"     component={ResultsScreen}     options={{ title: 'Resultados' }} />
      {/* Alerts tab hidden from bottom bar — accessible via notification icon on HomeScreen header */}
      <Tab.Screen name="Alerts"      component={AlertsScreen}      options={{ title: 'Alertas', tabBarButton: () => null, tabBarItemStyle: { display: 'none', width: 0, maxWidth: 0, minWidth: 0 } }} />
      <Tab.Screen name="Profile"     component={PlayerProfileScreen} options={{ title: 'Perfil' }} />
    </Tab.Navigator>
  );
}
