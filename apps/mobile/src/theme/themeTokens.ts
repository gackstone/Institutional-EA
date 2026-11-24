/**
 * Mobile Design Tokens — 100% synchronized with Desktop Design System.
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
}

export const DARK_THEME: ColorTokens = {
  background: "#0D0E11",
  surface: "#14171F",
  card: "#181C26",
  cardSecondary: "#212634",
  border: "rgba(255, 255, 255, 0.08)",
  borderSubtle: "rgba(255, 255, 255, 0.04)",
  text: "#F3F4F6",
  textMuted: "#9CA3AF",
  textDim: "#6B7280",
  accent: "#3B82F6",
  accentLight: "rgba(59, 130, 246, 0.15)",
  profit: "#22C55E",
  profitBg: "rgba(34, 197, 94, 0.15)",
  loss: "#EF4444",
  lossBg: "rgba(239, 68, 68, 0.15)",
  warning: "#F59E0B",
  warningBg: "rgba(245, 158, 11, 0.15)",
  chartBackground: "#0D0E11",
  chartGrid: "rgba(255, 255, 255, 0.05)",
  chartText: "#9CA3AF",
  bullCandle: "#0A997D",
  bearCandle: "#EE3749",
};

export const LIGHT_THEME: ColorTokens = {
  background: "#F5F6F8",
  surface: "#FFFFFF",
  card: "#FFFFFF",
  cardSecondary: "#F0F2F5",
  border: "rgba(0, 0, 0, 0.08)",
  borderSubtle: "rgba(0, 0, 0, 0.04)",
  text: "#0F172A",
  textMuted: "#64748B",
  textDim: "#94A3B8",
  accent: "#2563EB",
  accentLight: "rgba(37, 99, 235, 0.10)",
  profit: "#16A34A",
  profitBg: "rgba(22, 163, 74, 0.10)",
  loss: "#DC2626",
  lossBg: "rgba(220, 38, 38, 0.10)",
  warning: "#D97706",
  warningBg: "rgba(217, 119, 6, 0.10)",
  chartBackground: "#FFFFFF",
  chartGrid: "rgba(0, 0, 0, 0.05)",
  chartText: "#64748B",
  bullCandle: "#0A997D",
  bearCandle: "#EE3749",
};

export function getThemeTokens(mode: ThemeMode): ColorTokens {
  return mode === "light" ? LIGHT_THEME : DARK_THEME;
}
