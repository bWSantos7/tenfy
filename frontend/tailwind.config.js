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
          neon:        '#C6EF21',
          'neon-dark': '#B0D61E',
          lime:        '#C6EF21',
          'lime-dark': '#B0D61E',
          orange:      '#FF6A00',
          blue:        '#3B82F6',
          'blue-dark': '#2563EB',
        },
        brand: {
          lime:        '#C6EF21',
          'lime-dark': '#B0D61E',
          orange:      '#FF6A00',
          dark:        '#0A1330',
          navy:        '#0A1330',
        },
        text: {
          primary:   'rgb(var(--text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
          muted:     'rgb(var(--text-muted) / <alpha-value>)',
        },
        border: {
          subtle: 'rgb(var(--border-subtle) / <alpha-value>)',
          accent: '#C6EF2133',
        },
        status: {
          open:     '#C6EF21',
          closing:  '#FF6A00',
          closed:   '#94A3B8',
          drawn:    '#3B82F6',
          progress: '#8B5CF6',
          finished: '#64748B',
          canceled: '#EF4444',
        },
      },
      fontFamily: {
        sans: ['Poppins', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      boxShadow: {
        glow:        '0 0 24px rgba(198, 239, 33, 0.35)',
        'glow-lime': '0 0 24px rgba(198, 239, 33, 0.35)',
        card:        '0 2px 8px rgba(0, 0, 0, 0.08)',
        'card-dark': '0 4px 16px rgba(0, 0, 0, 0.40)',
      },
      keyframes: {
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.5' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
    },
  },
  plugins: [],
};
