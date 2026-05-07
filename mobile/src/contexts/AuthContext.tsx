import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { User } from '../types';
import { fetchMe, loadStoredUser, logout as logoutSvc } from '../services/auth';
import { fetchSubscription } from '../services/billing';
import { TOKEN_KEY, storage } from '../services/api';

// 'none'    = no subscription (Free tier)
// 'active'  = paid and active
// 'pending' = paid plan chosen but payment not confirmed yet → gate access
// other     = unpaid / expired / canceled
export type SubscriptionStatus = 'none' | 'active' | 'pending' | 'unpaid' | 'expired' | 'canceled' | 'trial' | null;

type AuthState = {
  user: User | null;
  ready: boolean;
  isAuthenticated: boolean;
  subscriptionStatus: SubscriptionStatus;
  setUser: (u: User | null) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState]                     = useState<User | null>(null);
  const [ready, setReady]                        = useState(false);
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatus>(null);

  const refresh = useCallback(async () => {
    const token = await storage.get(TOKEN_KEY);
    if (!token) {
      setUserState(null);
      setSubscriptionStatus(null);
      setReady(true);
      return;
    }
    try {
      const u = await fetchMe();
      setUserState(u);
      // Check subscription status — used by GatedTabs to block access until payment is confirmed
      try {
        const sub = await fetchSubscription();
        setSubscriptionStatus((sub?.status as SubscriptionStatus) ?? 'none');
      } catch {
        setSubscriptionStatus('none');
      }
    } catch {
      setUserState(null);
      setSubscriptionStatus(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const stored = await loadStoredUser();
      if (stored) setUserState(stored);
      await refresh();
    })();
  }, [refresh]);

  const logout = useCallback(async () => {
    await logoutSvc();
    setUserState(null);
    setSubscriptionStatus(null);
  }, []);

  const value = useMemo(() => ({
    user,
    ready,
    isAuthenticated: !!user,
    subscriptionStatus,
    setUser: setUserState,
    logout,
    refresh,
  }), [user, ready, subscriptionStatus, logout, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
