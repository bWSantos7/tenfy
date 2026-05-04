import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { User } from '../types';
import { fetchMe, loadStoredUser, logout as logoutSvc } from '../services/auth';
import { TOKEN_KEY, storage } from '../services/api';

type AuthState = {
  user: User | null;
  ready: boolean;
  isAuthenticated: boolean;
  setUser: (u: User | null) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    const token = await storage.get(TOKEN_KEY);
    if (!token) {
      setUserState(null);
      setReady(true);
      return;
    }
    try { setUserState(await fetchMe()); } catch { setUserState(null); } finally { setReady(true); }
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
  }, []);

  const value = useMemo(() => ({
    user,
    ready,
    isAuthenticated: !!user,
    setUser: setUserState,
    logout,
    refresh,
  }), [user, ready, logout, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
