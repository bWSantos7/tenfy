export type AppTheme = 'dark' | 'light';

// Tenfy brand palette — v2
// Azul Profundo: #0A1330 | Esmeralda: #10B981 | Laranja Barro: #FF6A00
// Off-white: #F6F7FA | Grafite: #1D232D
export const palette = {
  light: {
    bgBase: '#F6F7FA',
    bgCard: '#FFFFFF',
    bgElevated: '#EEF0F5',
    bgSubtle: '#F6F7FA',
    textPrimary: '#0A1330',
    textSecondary: '#3D4F6E',
    textMuted: '#8C9AB5',
    borderSubtle: '#DDE1EE',
    // Primary CTA in light mode = Azul Profundo (navy button, white text)
    accentNeon: '#0A1330',
    accentNeonDark: '#060D20',
    accentLime: '#10B981',
    accentOrange: '#FF6A00',
    accentBlue: '#3B82F6',
    statusOpen: '#10B981',
    statusClosing: '#FF6A00',
    statusClosed: '#8C9AB5',
    statusDrawn: '#3B82F6',
    statusProgress: '#8B5CF6',
    statusFinished: '#64748B',
    statusCanceled: '#EF4444',
    danger: '#EF4444',
    shadow: 'rgba(10,19,48,0.10)',
  },
  dark: {
    bgBase: '#0A1330',
    bgCard: '#1D232D',
    bgElevated: '#252D3D',
    bgSubtle: '#07101F',
    textPrimary: '#F6F7FA',
    textSecondary: '#AAB9CD',
    textMuted: '#5F738C',
    borderSubtle: '#2A3550',
    // Primary CTA in dark mode = Esmeralda (emerald button, white text)
    accentNeon: '#10B981',
    accentNeonDark: '#059669',
    accentLime: '#10B981',
    accentOrange: '#FF6A00',
    accentBlue: '#3B82F6',
    statusOpen: '#10B981',
    statusClosing: '#FF6A00',
    statusClosed: '#5F738C',
    statusDrawn: '#3B82F6',
    statusProgress: '#8B5CF6',
    statusFinished: '#475569',
    statusCanceled: '#EF4444',
    danger: '#EF4444',
    shadow: 'rgba(0,0,0,0.45)',
  },
};
