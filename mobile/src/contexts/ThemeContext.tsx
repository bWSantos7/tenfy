import React, { createContext, useContext, useMemo, useState } from 'react';
import { AppTheme, palette } from '../theme';

type ThemeContextType = {
  theme: AppTheme;
  colors: typeof palette.dark;
  toggle: () => void;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<AppTheme>('dark');
  const value = useMemo(() => ({
    theme,
    colors: palette[theme],
    toggle: () => setTheme((prev) => prev === 'dark' ? 'light' : 'dark'),
  }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used within ThemeProvider');
  return context;
}
