/**
 * Institutional EA Companion — Centralized Glassmorphism Design Tokens
 * Single Source of Truth sampled from the visual reference image.
 * Documented in companion/docs/DESIGN_SPEC.md.
 */

export const DESIGN_TOKENS = {
  colors: {
    bg: {
      canvas: "#091426",
      navyTop: "#0A152B",
      navyDeep: "#071020",
      royalGlow: "#2F497C",
      horizonGlow: "#7196CB",
      tealDepth: "#112B42",
    },
    surface: {
      glassCard: "rgba(21, 39, 74, 0.52)",
      glassElevated: "rgba(26, 48, 90, 0.72)",
      glassSidebarCollapsed: "rgba(10, 21, 43, 0.84)",
      glassSidebarExpanded: "rgba(11, 23, 47, 0.94)",
      glassTile: "rgba(20, 41, 66, 0.52)",
      tableHeader: "rgba(32, 54, 101, 0.34)",
      tableRowHover: "rgba(34, 61, 106, 0.48)",
      tableRowStripe: "rgba(22, 41, 78, 0.28)",
      pillControl: "rgba(24, 44, 82, 0.68)",
    },
    border: {
      glass: "rgba(186, 214, 255, 0.14)",
      glassHover: "rgba(186, 214, 255, 0.26)",
      glassStrong: "rgba(194, 240, 118, 0.38)",
      divider: "rgba(148, 179, 226, 0.11)",
    },
    accent: {
      lime: "#B0F648",
      limeSoft: "#C2F076",
      limeBright: "#99EF44",
      limeUnderline: "#C3E67E",
      limeMutedBg: "rgba(176, 246, 72, 0.14)",
      violet: "#C077FA",
      violetSoft: "#C9ACDA",
      violetMutedBg: "rgba(192, 119, 250, 0.16)",
      cyan: "#5EEAD4",
      cyanMutedBg: "rgba(94, 234, 212, 0.14)",
      royalBlue: "#4F8CFF",
    },
    semantic: {
      profit: "#B0F648",
      profitSoft: "rgba(176, 246, 72, 0.15)",
      danger: "#FF5A6E",
      dangerSoft: "rgba(255, 90, 110, 0.16)",
      warning: "#FBBF24",
      warningSoft: "rgba(251, 191, 36, 0.16)",
    },
    text: {
      primary: "#F4F7FF",
      secondary: "#B6C5E0",
      muted: "#8496B8",
      onLime: "#081321",
    },
    chart: {
      background: "#081223",
      gridLine: "rgba(113, 150, 203, 0.11)",
      axisText: "#8FA4C8",
      axisBorder: "rgba(148, 179, 226, 0.16)",
      crosshair: "rgba(176, 246, 72, 0.45)",
      crosshairLabelBg: "#122444",
      upCandle: "#B0F648",
      upWick: "#C2F076",
      downCandle: "#FF5A6E",
      downWick: "#FF7A8A",
    },
  },
  radii: {
    card: "18px",
    tile: "14px",
    button: "12px",
    pill: "9999px",
  },
  sidebar: {
    collapsedWidthPx: 60,
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
 * Returns circular coin/instrument icon chip styling modeled on the reference image's
 * neon-lime Ethereum and violet Cardano circular table chips.
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
