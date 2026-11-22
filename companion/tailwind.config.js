/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', '"SFMono-Regular"', '"Cascadia Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        arcade: {
          bg: "var(--arcade-bg)",
          card: "var(--arcade-card)",
          surface: "var(--arcade-surface)",
          secondary: "var(--arcade-surface-secondary)",
          surfaceSecondary: "var(--arcade-surface-secondary)",
          surfaceTertiary: "var(--arcade-surface-tertiary)",
          border: "var(--arcade-border)",
          borderSubtle: "var(--arcade-border-subtle)",
          borderStrong: "var(--arcade-border-strong)",
          text: "var(--arcade-text)",
          textSecondary: "var(--arcade-text-secondary)",
          textMuted: "var(--arcade-text-muted)",
          primary: "var(--arcade-primary)",
          primaryHover: "var(--arcade-primary-hover)",
          primaryActive: "var(--arcade-primary-active)",
          primarySoft: "var(--arcade-primary-soft)",
          profit: "var(--arcade-profit)",
          loss: "var(--arcade-loss)",
          error: "var(--arcade-error)",
          warning: "var(--arcade-warning)",
          info: "var(--arcade-info)",
        }
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgba(16, 42, 42, 0.04), 0 1px 2px -1px rgba(16, 42, 42, 0.03)',
        'pop': '0 10px 25px -5px rgba(16, 42, 42, 0.08), 0 8px 10px -6px rgba(16, 42, 42, 0.04)',
        'xs': '0 1px 2px rgba(19, 23, 34, 0.04)',
      }
    },
  },
  plugins: [],
}
