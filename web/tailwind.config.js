/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Every colour resolves to a CSS variable, so a component written once
        // works in both themes and no shade is ever hardcoded at a call site.
        bg: {
          DEFAULT: 'hsl(var(--bg) / <alpha-value>)',
          subtle: 'hsl(var(--bg-subtle) / <alpha-value>)',
        },
        surface: {
          DEFAULT: 'hsl(var(--surface) / <alpha-value>)',
          hover: 'hsl(var(--surface-hover) / <alpha-value>)',
          sunk: 'hsl(var(--surface-sunk) / <alpha-value>)',
        },
        line: {
          DEFAULT: 'hsl(var(--border) / <alpha-value>)',
          strong: 'hsl(var(--border-strong) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'hsl(var(--text) / <alpha-value>)',
          soft: 'hsl(var(--text-soft) / <alpha-value>)',
          muted: 'hsl(var(--text-muted) / <alpha-value>)',
          faint: 'hsl(var(--text-faint) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          hover: 'hsl(var(--accent-hover) / <alpha-value>)',
          soft: 'hsl(var(--accent-soft) / <alpha-value>)',
          fg: 'hsl(var(--accent-fg) / <alpha-value>)',
        },
        ok: {
          DEFAULT: 'hsl(var(--ok) / <alpha-value>)',
          soft: 'hsl(var(--ok-soft) / <alpha-value>)',
        },
        warn: {
          DEFAULT: 'hsl(var(--warn) / <alpha-value>)',
          soft: 'hsl(var(--warn-soft) / <alpha-value>)',
        },
        bad: {
          DEFAULT: 'hsl(var(--bad) / <alpha-value>)',
          soft: 'hsl(var(--bad-soft) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'hsl(var(--info) / <alpha-value>)',
          soft: 'hsl(var(--info-soft) / <alpha-value>)',
        },
        // Five-step compliance ramp. Scores need more resolution than a
        // pass/fail: 74 and 41 both fail, and should not look the same.
        score: {
          1: 'hsl(var(--score-1) / <alpha-value>)',
          2: 'hsl(var(--score-2) / <alpha-value>)',
          3: 'hsl(var(--score-3) / <alpha-value>)',
          4: 'hsl(var(--score-4) / <alpha-value>)',
          5: 'hsl(var(--score-5) / <alpha-value>)',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 4px)',
        sm: 'calc(var(--radius) - 6px)',
      },
      boxShadow: {
        xs: 'var(--shadow-xs)',
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Reserved for verdicts, scores and page titles. A serif at display
        // size is what stops a dense console reading as another admin template.
        display: ['Fraunces', 'Iowan Old Style', 'Georgia', 'serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
        // Editorial display sizes, tightened as they grow.
        'display-sm': ['1.75rem', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
        'display': ['2.5rem', { lineHeight: '1.05', letterSpacing: '-0.025em' }],
        'display-lg': ['3.5rem', { lineHeight: '1', letterSpacing: '-0.03em' }],
        'display-xl': ['4.5rem', { lineHeight: '0.95', letterSpacing: '-0.035em' }],
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.9)', opacity: '0.6' },
          '70%': { transform: 'scale(1.6)', opacity: '0' },
          '100%': { transform: 'scale(1.6)', opacity: '0' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-ring': 'pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
