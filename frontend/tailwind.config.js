/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          base:     'rgb(var(--bg-base) / <alpha-value>)',
          card:     'rgb(var(--bg-card) / <alpha-value>)',
          elevated: 'rgb(var(--bg-elevated) / <alpha-value>)',
          subtle:   'rgb(var(--bg-subtle) / <alpha-value>)',
          surface:  'rgb(var(--bg-elevated) / <alpha-value>)',
        },
        accent: {
          neon:        '#00FF88',
          'neon-dark': '#00CC6E',
          blue:        '#00B2FF',
          'blue-dark': '#0090CC',
        },
        text: {
          primary:   'rgb(var(--text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
          muted:     'rgb(var(--text-muted) / <alpha-value>)',
        },
        border: {
          subtle: 'rgb(var(--border-subtle) / <alpha-value>)',
          accent: '#00FF8833',
        },
        status: {
          open:     '#00FF88',
          closing:  '#FFB020',
          closed:   '#7A7A7A',
          drawn:    '#00B2FF',
          progress: '#A463F2',
          finished: '#5A5A5A',
          canceled: '#FF5A5A',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      boxShadow: {
        glow:       '0 0 24px rgba(0, 255, 136, 0.25)',
        'glow-blue':'0 0 24px rgba(0, 178, 255, 0.25)',
        card:       '0 4px 12px rgba(0, 0, 0, 0.5)',
      },
      keyframes: {
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.5' },
        },
      },
    },
  },
  plugins: [],
};
