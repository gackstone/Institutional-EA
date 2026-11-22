/**
 * Institutional EA Companion — Centralized Neutral Charcoal Design Tokens
 * Single Source of Truth sampled from IMAGE 1 ("Overlay") and IMAGE 2 (Sidebar).
 * Documented in companion/docs/THEME_SPEC.md.
 */

export const DESIGN_TOKENS = {
  colors: {
    bg: {
      canvas: "#0E0D0B",
      titlebar: "#12110F",
      panel: "#1E1D1B",
      panelTopLeft: "#2B2A26",
      panelMid: "#23221F",
      card: "#161513",
      inset: "#100F0D",
      elevated: "#242320",
      active: "#2B2A26",
    },
    sidebar: {
      expandedBg: "#191D20",
      collapsedBg: "#17181A",
      activeFill: "#272A2F",
      collapsedActiveFill: "#303135",
      border: "rgba(255, 255, 255, 0.08)",
      textActive: "#FFFFFF",
      textInactive: "#9CA1A6",
      treeLine: "#303437",
      logoTileBg: "#F8F8FA",
      badgeMintBg: "#A9ECDA",
      badgeMintText: "#0E1A16",
      badgePeachBg: "#F5C59F",
      badgePeachText: "#1F140B",
    },
    border: {
      subtle: "rgba(255, 255, 253, 0.07)",
      default: "rgba(255, 255, 253, 0.11)",
      strong: "#3A3935",
      divider: "rgba(255, 255, 253, 0.06)",
    },
    accent: {
      primary: "#F5F5F2",
      primaryHover: "#FFFFFF",
      onPrimary: "#121110",
    },
    semantic: {
      profit: "#6EE7B7",
      profitSolid: "#36B37E",
      profitSoft: "rgba(54, 179, 126, 0.14)",
      profitBorder: "rgba(110, 231, 183, 0.30)",
      danger: "#F07178",
      dangerSolid: "#D94854",
      dangerSoft: "rgba(217, 72, 84, 0.14)",
      dangerBorder: "rgba(240, 113, 120, 0.34)",
      warning: "#EAB354",
      warningSoft: "rgba(234, 179, 84, 0.14)",
      warningBorder: "rgba(234, 179, 84, 0.34)",
      info: "#5EC2C6",
      infoSoft: "rgba(94, 194, 198, 0.13)",
      infoBorder: "rgba(94, 194, 198, 0.34)",
    },
    text: {
      primary: "#F5F5F2",
      secondary: "#B4B3B0",
      muted: "#8A8986",
      dim: "#666562",
    },
    chart: {
      background: "#100F0D",
      gridLine: "rgba(255, 255, 253, 0.06)",
      axisText: "#8A8986",
      axisBorder: "rgba(255, 255, 253, 0.08)",
      crosshair: "rgba(245, 245, 242, 0.38)",
      crosshairLabelBg: "#242320",
      upCandle: "#36B37E",
      upWick: "#6EE7B7",
      downCandle: "#D94854",
      downWick: "#F07178",
    },
  },
  radii: {
    panel: "28px",
    sidebar: "20px",
    card: "16px",
    tile: "12px",
    button: "12px",
    pill: "9999px",
  },
  sidebar: {
    collapsedWidthPx: 76,
    expandedWidthPx: 264,
    collapseDelayMs: 140,
    transitionDurationMs: 220,
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
 * Neutral monochrome symbol chip styling for non-chart tables and cards.
 */
export function getNeutralSymbolChipSpec(symbol: string): SymbolAccentSpec {
  const upper = (symbol || "").toUpperCase();
  if (upper.includes("XAU") || upper.includes("GOLD")) {
    return {
      symbol,
      shortCode: "Au",
      chipBg: "bg-[#242320] text-[#F5F5F2]",
      chipText: "text-[#F5F5F2]",
      chipRing: "ring-1 ring-[#3A3935]",
      tagLabel: "Gold Spot",
    };
  }
  if (upper.includes("BTC")) {
    return {
      symbol,
      shortCode: "₿",
      chipBg: "bg-[#242320] text-[#F5F5F2]",
      chipText: "text-[#F5F5F2]",
      chipRing: "ring-1 ring-[#3A3935]",
      tagLabel: "Bitcoin 24/7",
    };
  }
  if (upper.includes("JPY")) {
    return {
      symbol,
      shortCode: "¥",
      chipBg: "bg-[#242320] text-[#F5F5F2]",
      chipText: "text-[#F5F5F2]",
      chipRing: "ring-1 ring-[#3A3935]",
      tagLabel: "FX Inverse",
    };
  }
  return {
    symbol,
    shortCode: upper.slice(0, 2) || "FX",
    chipBg: "bg-[#242320] text-[#F5F5F2]",
    chipText: "text-[#F5F5F2]",
    chipRing: "ring-1 ring-[#3A3935]",
    tagLabel: "Instrument",
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
