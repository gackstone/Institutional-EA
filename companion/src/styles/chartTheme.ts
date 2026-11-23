/**
 * TradingView Light Chart Theme — Single Source of Truth.
 * All colors sampled directly from the uploaded reference image (1024x478).
 *
 * Change BULL_COLOR or BEAR_COLOR in one line to recolor all candlesticks.
 */

export const BULL_COLOR = "#0A997D"; // Sampled bullish teal from reference image
export const BEAR_COLOR = "#EE3749"; // Sampled bearish red from reference image

/**
 * LuxAlgo Smart Money Concepts (Pine v5, CC BY-NC-SA 4.0 © LuxAlgo) Palette Tokens.
 * Centralized so Colored / Monochrome modes and user overrides read from one source.
 */
export const LUXALGO_SMC_PALETTE = {
  colored: {
    green: "#089981",
    red: "#F23645",
    blue: "#2157f3",
    gray: "#878b94",
    internalBullOb: "rgba(49, 121, 245, 0.20)",
    internalBearOb: "rgba(247, 124, 128, 0.20)",
    swingBullOb: "rgba(24, 72, 204, 0.20)",
    swingBearOb: "rgba(178, 40, 51, 0.20)",
    swingBullObBorder: "rgba(24, 72, 204, 0.85)",
    swingBearObBorder: "rgba(178, 40, 51, 0.85)",
    bullFvg: "rgba(0, 255, 104, 0.30)",
    bearFvg: "rgba(255, 0, 8, 0.30)",
    premiumZone: "rgba(242, 54, 69, 0.20)",
    equilibriumZone: "rgba(135, 139, 148, 0.20)",
    discountZone: "rgba(8, 153, 129, 0.20)",
  },
  monochrome: {
    bull: "#b2b5be",
    bear: "#5d606b",
    neutral: "#878b94",
    internalBullOb: "rgba(178, 181, 190, 0.20)",
    internalBearOb: "rgba(93, 96, 107, 0.20)",
    swingBullOb: "rgba(178, 181, 190, 0.20)",
    swingBearOb: "rgba(93, 96, 107, 0.20)",
    swingBullObBorder: "rgba(178, 181, 190, 0.85)",
    swingBearObBorder: "rgba(93, 96, 107, 0.85)",
    bullFvg: "rgba(178, 181, 190, 0.28)",
    bearFvg: "rgba(93, 96, 107, 0.28)",
    premiumZone: "rgba(93, 96, 107, 0.20)",
    equilibriumZone: "rgba(135, 139, 148, 0.20)",
    discountZone: "rgba(178, 181, 190, 0.20)",
  },
  labelSizesPx: {
    Tiny: 9.5,
    Small: 11,
    Normal: 12.5,
  },
} as const;

export const CHART_TV_LIGHT_THEME = {
  background: "#FFFFFF",
  gridLine: "rgba(226, 232, 240, 0.45)", // Barely visible 1px light-gray grid
  axisText: "#4B5563",
  axisBorder: "#E5E7EB",
  crosshairLine: "#787B86",
  crosshairLabelBg: "#374151",

  candles: {
    bull: BULL_COLOR,
    bear: BEAR_COLOR,
  },

  // Long & Short Position Template (using Long template's sampled values for both)
  position: {
    // Composites to sampled #A8DCD4 on #FFFFFF
    profitFillPrimary: "rgba(10, 153, 125, 0.34)",
    // Composites to sampled #CCECE8 on #FFFFFF (short right extension)
    profitFillExtension: "rgba(10, 153, 125, 0.19)",
    // Composites to sampled #FCD8DC on #FFFFFF
    lossFill: "rgba(238, 55, 73, 0.15)",

    // Secondary/older overlapping trade capped opacity
    secondaryOpacityScale: 0.55,
    // Pending signal opacity
    pendingOpacityScale: 0.5,

    // Clean subtle 1px edges & lines
    tpEdge: "rgba(10, 153, 125, 0.55)",
    tp1InnerDashed: "rgba(10, 153, 125, 0.48)",
    slEdge: "rgba(238, 55, 73, 0.50)",
    entryLine: "#787B86",
    pathDashedLine: "rgba(100, 116, 139, 0.65)",
  },

  // FVG & OB Boxes (composites to sampled #D8F0D8 on #FFFFFF, no heavy border)
  fvgOb: {
    fill: "rgba(110, 198, 114, 0.30)",
    mitigatedFill: "rgba(110, 198, 114, 0.14)",
  },

  // Muted text-free overlays readable on white background
  layers: {
    liquidityLine: "rgba(100, 116, 139, 0.38)",
    structureLine: "rgba(71, 85, 105, 0.42)",
    structureDot: "rgba(71, 85, 105, 0.55)",
    sessionBand: "rgba(148, 163, 184, 0.08)",
  },

  // Typography (the ONLY allowed plot labels: LONG/SHORT POSITION & FVG/OB)
  typography: {
    fontFamily: '"Plus Jakarta Sans Variable", "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    axisFontFamily: '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
    labelColor: "#313131",
    positionLabelSize: "clamp(10px, 0.78vw, 12px)",
    boxLabelSize: "clamp(10px, 0.72vw, 11px)",
  },
} as const;
