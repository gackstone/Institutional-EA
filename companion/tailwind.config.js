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
        "institutional-ea": {
          bg: "var(--institutional-ea-bg)",
          card: "var(--institutional-ea-card)",
          surface: "var(--institutional-ea-surface)",
          secondary: "var(--institutional-ea-surface-secondary)",
          surfaceSecondary: "var(--institutional-ea-surface-secondary)",
          surfaceTertiary: "var(--institutional-ea-surface-tertiary)",
          border: "var(--institutional-ea-border)",
          borderSubtle: "var(--institutional-ea-border-subtle)",
          borderStrong: "var(--institutional-ea-border-strong)",
          text: "var(--institutional-ea-text)",
          textSecondary: "var(--institutional-ea-text-secondary)",
          textMuted: "var(--institutional-ea-text-muted)",
          primary: "var(--institutional-ea-primary)",
          primaryHover: "var(--institutional-ea-primary-hover)",
          primaryActive: "var(--institutional-ea-primary-active)",
          primarySoft: "var(--institutional-ea-primary-soft)",
          profit: "var(--institutional-ea-profit)",
          loss: "var(--institutional-ea-loss)",
          error: "var(--institutional-ea-error)",
          warning: "var(--institutional-ea-warning)",
          info: "var(--institutional-ea-info)",
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
