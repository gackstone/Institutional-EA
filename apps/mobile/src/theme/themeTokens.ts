/**
 * Mobile Design Tokens — Mint-Green (#6FF2C4) + Deep Navy brand palette
 * synchronized with the Institutional EA brain logo & Desktop Chart Theme.
 */

export type ThemeMode = "dark" | "light";

export interface ColorTokens {
  background: string;
  surface: string;
  card: string;
  cardSecondary: string;
  border: string;
  borderSubtle: string;
  text: string;
  textMuted: string;
  textDim: string;
  accent: string;
  accentText: string;
  accentLight: string;
  profit: string;
  profitBg: string;
  loss: string;
  lossBg: string;
  warning: string;
  warningBg: string;
  chartBackground: string;
  chartGrid: string;
  chartText: string;
  bullCandle: string;
  bearCandle: string;
  overlayBg: string;
}

export const DARK_THEME: ColorTokens = {
  background: "#0B0F19",
  surface: "#111827",
  card: "#161E2E",
  cardSecondary: "#1F293D",
  border: "rgba(111, 242, 196, 0.14)",
  borderSubtle: "rgba(255, 255, 255, 0.06)",
  text: "#F3F6FA",
  textMuted: "#9CA8BC",
  textDim: "#6B7890",
  accent: "#6FF2C4",
  accentText: "#062019",
  accentLight: "rgba(111, 242, 196, 0.14)",
  profit: "#10B981",
  profitBg: "rgba(16, 185, 129, 0.16)",
  loss: "#EF4444",
  lossBg: "rgba(239, 68, 68, 0.16)",
  warning: "#F59E0B",
  warningBg: "rgba(245, 158, 11, 0.16)",
  chartBackground: "#0D0E11",
  chartGrid: "rgba(255, 255, 255, 0.05)",
  chartText: "#9CA3AF",
  bullCandle: "#0A997D",
  bearCandle: "#EE3749",
  overlayBg: "rgba(5, 8, 15, 0.78)",
};

export const LIGHT_THEME: ColorTokens = {
  background: "#F4F7FA",
  surface: "#FFFFFF",
  card: "#FFFFFF",
  cardSecondary: "#EDF2F7",
  border: "rgba(15, 23, 42, 0.10)",
  borderSubtle: "rgba(15, 23, 42, 0.05)",
  text: "#0F172A",
  textMuted: "#475569",
  textDim: "#94A3B8",
  accent: "#0D9488",
  accentText: "#FFFFFF",
  accentLight: "rgba(13, 148, 136, 0.12)",
  profit: "#059669",
  profitBg: "rgba(5, 150, 105, 0.12)",
  loss: "#DC2626",
  lossBg: "rgba(220, 38, 38, 0.12)",
  warning: "#D97706",
  warningBg: "rgba(217, 119, 6, 0.12)",
  chartBackground: "#FFFFFF",
  chartGrid: "rgba(0, 0, 0, 0.05)",
  chartText: "#64748B",
  bullCandle: "#0A997D",
  bearCandle: "#EE3749",
  overlayBg: "rgba(15, 23, 42, 0.45)",
};

export function getThemeTokens(mode: ThemeMode): ColorTokens {
  return mode === "light" ? LIGHT_THEME : DARK_THEME;
}
