/**
 * Institutional EA Companion — Centralized BM Forex Hub Design Tokens
 * Single Source of Truth for Global Theme (Colors, Radii, Spacing, Sidebar).
 */

export const DESIGN_TOKENS = {
  colors: {
    bg: {
      canvas: "#0A0A0C",
      titlebar: "#0A0A0C",
      panel: "#0A0A0C",
      panelTopLeft: "#101114",
      panelMid: "#101114",
      card: "#111216",
      cardAlt: "#121317",
      inset: "#0D0E11",
      elevated: "#16181D",
      active: "#1D2026",
    },
    sidebar: {
      expandedBg: "#0D0E12",
      collapsedBg: "#0D0E12",
      activeFill: "rgba(59, 130, 246, 0.14)",
      collapsedActiveFill: "rgba(59, 130, 246, 0.16)",
      border: "rgba(255, 255, 255, 0.06)",
      textActive: "#3B82F6",
      textInactive: "#8E95A5",
      treeLine: "rgba(255, 255, 255, 0.08)",
      logoTileBg: "#3B82F6",
      badgeMintBg: "rgba(59, 130, 246, 0.16)",
      badgeMintText: "#60A5FA",
      badgePeachBg: "rgba(239, 68, 68, 0.16)",
      badgePeachText: "#F87171",
    },
    border: {
      subtle: "rgba(255, 255, 255, 0.06)",
      default: "rgba(255, 255, 255, 0.09)",
      strong: "rgba(255, 255, 255, 0.14)",
      divider: "rgba(255, 255, 255, 0.06)",
    },
    accent: {
      primary: "#3B82F6",
      primaryHover: "#2563EB",
      primarySoft: "rgba(59, 130, 246, 0.14)",
      primaryBorder: "rgba(59, 130, 246, 0.32)",
      onPrimary: "#FFFFFF",
    },
    semantic: {
      profit: "#22C55E",
      profitSolid: "#22C55E",
      profitSoft: "rgba(34, 197, 94, 0.14)",
      profitBorder: "rgba(34, 197, 94, 0.28)",
      danger: "#EF4444",
      dangerSolid: "#EF4444",
      dangerSoft: "rgba(239, 68, 68, 0.14)",
      dangerBorder: "rgba(239, 68, 68, 0.28)",
      warning: "#F59E0B",
      warningSoft: "rgba(245, 158, 11, 0.14)",
      warningBorder: "rgba(245, 158, 11, 0.28)",
      info: "#3B82F6",
      infoSoft: "rgba(59, 130, 246, 0.14)",
      infoBorder: "rgba(59, 130, 246, 0.28)",
    },
    text: {
      primary: "#F3F4F6",
      secondary: "#9CA3AF",
      muted: "#6B7280",
      dim: "#4B5563",
    },
    chart: {
      background: "#0D0E11",
      gridLine: "rgba(255, 255, 255, 0.05)",
      axisText: "#6B7280",
      axisBorder: "rgba(255, 255, 255, 0.07)",
      crosshair: "rgba(59, 130, 246, 0.45)",
      crosshairLabelBg: "#16181D",
      upCandle: "#22C55E",
      upWick: "#22C55E",
      downCandle: "#EF4444",
      downWick: "#EF4444",
    },
  },
  radii: {
    panel: "0px",
    sidebar: "0px",
    card: "18px",
    tile: "12px",
    button: "10px",
    pill: "9999px",
  },
  spacing: {
    pagePaddingPx: 24,
    cardGapPx: 18,
  },
  sidebar: {
    collapsedWidthPx: 72,
    expandedWidthPx: 256,
    collapseDelayMs: 120,
    transitionDurationMs: 200,
  },
} as const;

export type SymbolAccentSpec = {
  symbol: string;
  shortCode: string;
  chipBg: string;
  chipText: string;
  chipRing: string;
  tagLabel: string;
};

/**
 * Circular symbol badge styling for watchlist, non-chart tables, and cards.
 */
export function getNeutralSymbolChipSpec(symbol: string): SymbolAccentSpec {
  const upper = (symbol || "").toUpperCase();
  if (upper.includes("XAU") || upper.includes("GOLD")) {
    return {
      symbol,
      shortCode: "Au",
      chipBg: "bg-[var(--iea-warning-soft)] text-[var(--iea-warning)]",
      chipText: "text-[var(--iea-warning)]",
      chipRing: "ring-1 ring-[var(--iea-warning-border)]",
      tagLabel: "Gold Spot / USD",
    };
  }
  if (upper.includes("BTC")) {
    return {
      symbol,
      shortCode: "₿",
      chipBg: "bg-[var(--iea-accent-primary-soft)] text-[var(--iea-accent-primary)]",
      chipText: "text-[var(--iea-accent-primary)]",
      chipRing: "ring-1 ring-[var(--iea-accent-primary-border)]",
      tagLabel: "Bitcoin / USD",
    };
  }
  if (upper.includes("JPY")) {
    return {
      symbol,
      shortCode: "¥",
      chipBg: "bg-[var(--iea-surface-elevated)] text-[var(--iea-text-primary)]",
      chipText: "text-[var(--iea-text-primary)]",
      chipRing: "ring-1 ring-[var(--iea-border-default)]",
      tagLabel: "US Dollar / Yen",
    };
  }
  return {
    symbol,
    shortCode: upper.slice(0, 2) || "FX",
    chipBg: "bg-[var(--iea-surface-elevated)] text-[var(--iea-text-primary)]",
    chipText: "text-[var(--iea-text-primary)]",
    chipRing: "ring-1 ring-[var(--iea-border-default)]",
    tagLabel: "FX Instrument",
  };
}

/**
 * Preserved verbatim for LiveTradingChart.tsx (Chart Protection Rule — DO NOT ALTER).
 */
export function getSymbolChipSpec(symbol: string): SymbolAccentSpec {
  const upper = (symbol || "").toUpperCase();
  if (upper.includes("XAU") || upper.includes("GOLD")) {
    return {
      symbol,
      shortCode: "Au",
      chipBg: "bg-[#B0F648] text-[#081321]",
      chipText: "text-[#081321]",
      chipRing: "ring-2 ring-[#B0F648]/35 shadow-[0_0_14px_rgba(176,246,72,0.38)]",
      tagLabel: "Gold Spot",
    };
  }
  if (upper.includes("BTC")) {
    return {
      symbol,
      shortCode: "₿",
      chipBg: "bg-[#C077FA] text-[#091426]",
      chipText: "text-[#091426]",
      chipRing: "ring-2 ring-[#C077FA]/35 shadow-[0_0_14px_rgba(192,119,250,0.38)]",
      tagLabel: "Bitcoin 24/7",
    };
  }
  if (upper.includes("JPY")) {
    return {
      symbol,
      shortCode: "¥",
      chipBg: "bg-[#5EEAD4] text-[#081321]",
      chipText: "text-[#081321]",
      chipRing: "ring-2 ring-[#5EEAD4]/35 shadow-[0_0_14px_rgba(94,234,212,0.35)]",
      tagLabel: "FX Inverse",
    };
  }
  return {
    symbol,
    shortCode: upper.slice(0, 2) || "FX",
    chipBg: "bg-[#4F8CFF] text-white",
    chipText: "text-white",
    chipRing: "ring-2 ring-[#4F8CFF]/35",
    tagLabel: "Instrument",
  };
}
