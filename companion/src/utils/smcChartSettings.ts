/**
 * LuxAlgo Smart Money Concepts — Chart Settings Schema & Persistence.
 * Mirrors the LuxAlgo "Smart Money Concepts" Pine v5 Inputs / Style / Visibility tabs.
 * Persisted via readVersionedState / writeVersionedState with safe fallback to defaults.
 */

import type { StorageLike } from "./persistedState";

export type SmcMode = "Historical" | "Present";
export type SmcStyle = "Colored" | "Monochrome";
export type StructureFilter = "All" | "BOS" | "CHoCH";
export type LabelSizeOption = "Tiny" | "Small" | "Normal";
export type ObFilterOption = "Atr" | "Cumulative Mean Range";
export type ObMitigationOption = "High/Low" | "Close";
export type FvgTimeframeOption = "Chart" | "M15" | "H1" | "H4" | "D1";
export type LineStyleOption = "solid" | "dashed" | "dotted";

export interface SmcChartSettings {
  settingsVersion: number;

  // Smart Money Concepts
  mode: SmcMode;
  style: SmcStyle;
  colorCandles: boolean;

  // Real Time Internal Structure
  showInternalStructure: boolean;
  internalBullishFilter: StructureFilter;
  internalBullishColor: string;
  internalBearishFilter: StructureFilter;
  internalBearishColor: string;
  internalConfluenceFilter: boolean;
  internalLabelSize: LabelSizeOption;

  // Real Time Swing Structure
  showSwingStructure: boolean;
  swingBullishFilter: StructureFilter;
  swingBullishColor: string;
  swingBearishFilter: StructureFilter;
  swingBearishColor: string;
  swingLabelSize: LabelSizeOption;
  showSwingPoints: boolean;
  swingPointsLength: number;
  showStrongWeakHL: boolean;

  // Order Blocks
  showInternalOB: boolean;
  internalOBCount: number;
  showSwingOB: boolean;
  swingOBCount: number;
  obFilter: ObFilterOption;
  obMitigation: ObMitigationOption;
  internalBullOBColor: string;
  internalBearOBColor: string;
  swingBullOBColor: string;
  swingBearOBColor: string;

  // EQH / EQL
  showEqhEql: boolean;
  eqhBarsConfirmation: number;
  eqhThreshold: number;
  eqhLabelSize: LabelSizeOption;

  // Fair Value Gaps
  showFvg: boolean;
  fvgAutoThreshold: boolean;
  fvgTimeframe: FvgTimeframeOption;
  fvgBullColor: string;
  fvgBearColor: string;
  fvgExtend: number;

  // Highs & Lows MTF
  showDailyHL: boolean;
  dailyStyle: LineStyleOption;
  dailyColor: string;
  showWeeklyHL: boolean;
  weeklyStyle: LineStyleOption;
  weeklyColor: string;
  showMonthlyHL: boolean;
  monthlyStyle: LineStyleOption;
  monthlyColor: string;

  // Premium & Discount Zones
  showPremiumDiscount: boolean;
  premiumColor: string;
  equilibriumColor: string;
  discountColor: string;

  // IRL / ERL Filters
  showIRL: boolean;
  showERL: boolean;

  // Companion Layers & Timeframe Visibility
  showSessions: boolean;
  showTrades: boolean;
  visibleTimeframes: {
    M1: boolean;
    M5: boolean;
    M15: boolean;
    H1: boolean;
    H4: boolean;
  };
}

export const SMC_SETTINGS_VERSION = 1;
export const SMC_SETTINGS_STORAGE_KEY = "iea_smc_chart_settings_v1";

export const SMC_PALETTE_TOKENS = {
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
} as const;

const C = SMC_PALETTE_TOKENS.colored;

export const DEFAULT_SMC_CHART_SETTINGS: SmcChartSettings = {
  settingsVersion: SMC_SETTINGS_VERSION,

  // Smart Money Concepts
  mode: "Historical",
  style: "Colored",
  colorCandles: false,

  // Real Time Internal Structure
  showInternalStructure: true,
  internalBullishFilter: "All",
  internalBullishColor: C.green,
  internalBearishFilter: "All",
  internalBearishColor: C.red,
  internalConfluenceFilter: false,
  internalLabelSize: "Tiny",

  // Real Time Swing Structure
  showSwingStructure: true,
  swingBullishFilter: "All",
  swingBullishColor: C.green,
  swingBearishFilter: "All",
  swingBearishColor: C.red,
  swingLabelSize: "Small",
  showSwingPoints: false,
  swingPointsLength: 50,
  showStrongWeakHL: true,

  // Order Blocks
  showInternalOB: true,
  internalOBCount: 5,
  showSwingOB: false,
  swingOBCount: 5,
  obFilter: "Atr",
  obMitigation: "High/Low",
  internalBullOBColor: C.internalBullOb,
  internalBearOBColor: C.internalBearOb,
  swingBullOBColor: C.swingBullOb,
  swingBearOBColor: C.swingBearOb,

  // EQH / EQL
  showEqhEql: true,
  eqhBarsConfirmation: 3,
  eqhThreshold: 0.1,
  eqhLabelSize: "Tiny",

  // Fair Value Gaps (kept on by default to match existing bot FVG/OB layer default)
  showFvg: true,
  fvgAutoThreshold: true,
  fvgTimeframe: "Chart",
  fvgBullColor: C.bullFvg,
  fvgBearColor: C.bearFvg,
  fvgExtend: 1,

  // Highs & Lows MTF
  showDailyHL: true,
  dailyStyle: "solid",
  dailyColor: C.blue,
  showWeeklyHL: true,
  weeklyStyle: "solid",
  weeklyColor: C.blue,
  showMonthlyHL: false,
  monthlyStyle: "solid",
  monthlyColor: C.blue,

  // Premium & Discount Zones
  showPremiumDiscount: false,
  premiumColor: C.premiumZone,
  equilibriumColor: C.equilibriumZone,
  discountColor: C.discountZone,

  // IRL / ERL Filters
  showIRL: true,
  showERL: true,

  // Companion Layers & Timeframe Visibility
  showSessions: true,
  showTrades: true,
  visibleTimeframes: {
    M1: true,
    M5: true,
    M15: true,
    H1: true,
    H4: true,
  },
};

export function cloneDefaultSmcSettings(): SmcChartSettings {
  return {
    ...DEFAULT_SMC_CHART_SETTINGS,
    visibleTimeframes: { ...DEFAULT_SMC_CHART_SETTINGS.visibleTimeframes },
  };
}

function isOneOf<T extends string>(val: unknown, allowed: readonly T[]): val is T {
  return typeof val === "string" && (allowed as readonly string[]).includes(val);
}

function clampNum(val: unknown, min: number, max: number, fallback: number): number {
  if (typeof val !== "number" || !Number.isFinite(val)) return fallback;
  return Math.min(max, Math.max(min, val));
}

function strColor(val: unknown, fallback: string): string {
  return typeof val === "string" && val.trim().length > 0 ? val.trim() : fallback;
}

export function sanitizeSmcChartSettings(raw: unknown): SmcChartSettings {
  const d = cloneDefaultSmcSettings();
  if (!raw || typeof raw !== "object") return d;
  const o = raw as Record<string, unknown>;
  const vt = (o.visibleTimeframes && typeof o.visibleTimeframes === "object"
    ? o.visibleTimeframes
    : {}) as Record<string, unknown>;

  return {
    settingsVersion: SMC_SETTINGS_VERSION,
    mode: isOneOf(o.mode, ["Historical", "Present"] as const) ? o.mode : d.mode,
    style: isOneOf(o.style, ["Colored", "Monochrome"] as const) ? o.style : d.style,
    colorCandles: typeof o.colorCandles === "boolean" ? o.colorCandles : d.colorCandles,

    showInternalStructure:
      typeof o.showInternalStructure === "boolean" ? o.showInternalStructure : d.showInternalStructure,
    internalBullishFilter: isOneOf(o.internalBullishFilter, ["All", "BOS", "CHoCH"] as const)
      ? o.internalBullishFilter
      : d.internalBullishFilter,
    internalBullishColor: strColor(o.internalBullishColor, d.internalBullishColor),
    internalBearishFilter: isOneOf(o.internalBearishFilter, ["All", "BOS", "CHoCH"] as const)
      ? o.internalBearishFilter
      : d.internalBearishFilter,
    internalBearishColor: strColor(o.internalBearishColor, d.internalBearishColor),
    internalConfluenceFilter:
      typeof o.internalConfluenceFilter === "boolean"
        ? o.internalConfluenceFilter
        : d.internalConfluenceFilter,
    internalLabelSize: isOneOf(o.internalLabelSize, ["Tiny", "Small", "Normal"] as const)
      ? o.internalLabelSize
      : d.internalLabelSize,

    showSwingStructure:
      typeof o.showSwingStructure === "boolean" ? o.showSwingStructure : d.showSwingStructure,
    swingBullishFilter: isOneOf(o.swingBullishFilter, ["All", "BOS", "CHoCH"] as const)
      ? o.swingBullishFilter
      : d.swingBullishFilter,
    swingBullishColor: strColor(o.swingBullishColor, d.swingBullishColor),
    swingBearishFilter: isOneOf(o.swingBearishFilter, ["All", "BOS", "CHoCH"] as const)
      ? o.swingBearishFilter
      : d.swingBearishFilter,
    swingBearishColor: strColor(o.swingBearishColor, d.swingBearishColor),
    swingLabelSize: isOneOf(o.swingLabelSize, ["Tiny", "Small", "Normal"] as const)
      ? o.swingLabelSize
      : d.swingLabelSize,
    showSwingPoints: typeof o.showSwingPoints === "boolean" ? o.showSwingPoints : d.showSwingPoints,
    swingPointsLength: Math.round(clampNum(o.swingPointsLength, 10, 200, d.swingPointsLength)),
    showStrongWeakHL: typeof o.showStrongWeakHL === "boolean" ? o.showStrongWeakHL : d.showStrongWeakHL,

    showInternalOB: typeof o.showInternalOB === "boolean" ? o.showInternalOB : d.showInternalOB,
    internalOBCount: Math.round(clampNum(o.internalOBCount, 1, 20, d.internalOBCount)),
    showSwingOB: typeof o.showSwingOB === "boolean" ? o.showSwingOB : d.showSwingOB,
    swingOBCount: Math.round(clampNum(o.swingOBCount, 1, 20, d.swingOBCount)),
    obFilter: isOneOf(o.obFilter, ["Atr", "Cumulative Mean Range"] as const) ? o.obFilter : d.obFilter,
    obMitigation: isOneOf(o.obMitigation, ["High/Low", "Close"] as const)
      ? o.obMitigation
      : d.obMitigation,
    internalBullOBColor: strColor(o.internalBullOBColor, d.internalBullOBColor),
    internalBearOBColor: strColor(o.internalBearOBColor, d.internalBearOBColor),
    swingBullOBColor: strColor(o.swingBullOBColor, d.swingBullOBColor),
    swingBearOBColor: strColor(o.swingBearOBColor, d.swingBearOBColor),

    showEqhEql: typeof o.showEqhEql === "boolean" ? o.showEqhEql : d.showEqhEql,
    eqhBarsConfirmation: Math.round(clampNum(o.eqhBarsConfirmation, 1, 20, d.eqhBarsConfirmation)),
    eqhThreshold: Number(clampNum(o.eqhThreshold, 0, 0.5, d.eqhThreshold).toFixed(2)),
    eqhLabelSize: isOneOf(o.eqhLabelSize, ["Tiny", "Small", "Normal"] as const)
      ? o.eqhLabelSize
      : d.eqhLabelSize,

    showFvg: typeof o.showFvg === "boolean" ? o.showFvg : d.showFvg,
    fvgAutoThreshold: typeof o.fvgAutoThreshold === "boolean" ? o.fvgAutoThreshold : d.fvgAutoThreshold,
    fvgTimeframe: isOneOf(o.fvgTimeframe, ["Chart", "M15", "H1", "H4", "D1"] as const)
      ? o.fvgTimeframe
      : d.fvgTimeframe,
    fvgBullColor: strColor(o.fvgBullColor, d.fvgBullColor),
    fvgBearColor: strColor(o.fvgBearColor, d.fvgBearColor),
    fvgExtend: Math.round(clampNum(o.fvgExtend, 0, 20, d.fvgExtend)),

    showDailyHL: typeof o.showDailyHL === "boolean" ? o.showDailyHL : d.showDailyHL,
    dailyStyle: isOneOf(o.dailyStyle, ["solid", "dashed", "dotted"] as const) ? o.dailyStyle : d.dailyStyle,
    dailyColor: strColor(o.dailyColor, d.dailyColor),
    showWeeklyHL: typeof o.showWeeklyHL === "boolean" ? o.showWeeklyHL : d.showWeeklyHL,
    weeklyStyle: isOneOf(o.weeklyStyle, ["solid", "dashed", "dotted"] as const)
      ? o.weeklyStyle
      : d.weeklyStyle,
    weeklyColor: strColor(o.weeklyColor, d.weeklyColor),
    showMonthlyHL: typeof o.showMonthlyHL === "boolean" ? o.showMonthlyHL : d.showMonthlyHL,
    monthlyStyle: isOneOf(o.monthlyStyle, ["solid", "dashed", "dotted"] as const)
      ? o.monthlyStyle
      : d.monthlyStyle,
    monthlyColor: strColor(o.monthlyColor, d.monthlyColor),

    showPremiumDiscount:
      typeof o.showPremiumDiscount === "boolean" ? o.showPremiumDiscount : d.showPremiumDiscount,
    premiumColor: strColor(o.premiumColor, d.premiumColor),
    equilibriumColor: strColor(o.equilibriumColor, d.equilibriumColor),
    discountColor: strColor(o.discountColor, d.discountColor),

    showIRL: typeof o.showIRL === "boolean" ? o.showIRL : d.showIRL,
    showERL: typeof o.showERL === "boolean" ? o.showERL : d.showERL,

    showSessions: typeof o.showSessions === "boolean" ? o.showSessions : d.showSessions,
    showTrades: typeof o.showTrades === "boolean" ? o.showTrades : d.showTrades,
    visibleTimeframes: {
      M1: typeof vt.M1 === "boolean" ? vt.M1 : true,
      M5: typeof vt.M5 === "boolean" ? vt.M5 : true,
      M15: typeof vt.M15 === "boolean" ? vt.M15 : true,
      H1: typeof vt.H1 === "boolean" ? vt.H1 : true,
      H4: typeof vt.H4 === "boolean" ? vt.H4 : true,
    },
  };
}

export function isValidSmcChartSettings(v: unknown): v is SmcChartSettings {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    o.settingsVersion === SMC_SETTINGS_VERSION &&
    isOneOf(o.mode, ["Historical", "Present"] as const) &&
    isOneOf(o.style, ["Colored", "Monochrome"] as const) &&
    typeof o.showInternalStructure === "boolean" &&
    typeof o.showSwingStructure === "boolean" &&
    typeof o.showInternalOB === "boolean" &&
    typeof o.showFvg === "boolean" &&
    typeof o.showIRL === "boolean" &&
    typeof o.showERL === "boolean" &&
    typeof o.showSessions === "boolean" &&
    typeof o.showTrades === "boolean"
  );
}

function resolveStorage(override?: StorageLike | null): StorageLike | null {
  if (override !== undefined) return override;
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // ignore
  }
  return null;
}

export function loadSmcChartSettings(storageOverride?: StorageLike | null): SmcChartSettings {
  const storage = resolveStorage(storageOverride);
  const fallback = cloneDefaultSmcSettings();
  if (!storage) return fallback;
  try {
    const rawStr = storage.getItem(SMC_SETTINGS_STORAGE_KEY);
    if (!rawStr) return fallback;
    const parsed = JSON.parse(rawStr);
    const candidate =
      parsed && typeof parsed === "object" && "data" in parsed ? (parsed as any).data : parsed;
    if (isValidSmcChartSettings(candidate)) {
      return sanitizeSmcChartSettings(candidate);
    }
    const sanitized = sanitizeSmcChartSettings(candidate);
    saveSmcChartSettings(sanitized, storage);
    return sanitized;
  } catch {
    saveSmcChartSettings(fallback, storage);
    return fallback;
  }
}

export function saveSmcChartSettings(
  settings: SmcChartSettings,
  storageOverride?: StorageLike | null
): boolean {
  const storage = resolveStorage(storageOverride);
  if (!storage) return false;
  try {
    storage.setItem(
      SMC_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: SMC_SETTINGS_VERSION,
        updatedAt: new Date().toISOString(),
        data: settings,
      })
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Derive the 5 toolbar layer chip states from SmcChartSettings (single source of truth).
 */
export function deriveLayerChipStates(s: SmcChartSettings) {
  return {
    liquidity: s.showEqhEql || s.showStrongWeakHL || s.showDailyHL || s.showWeeklyHL || s.showMonthlyHL,
    fvgOb: s.showInternalOB || s.showSwingOB || s.showFvg,
    structure: s.showInternalStructure || s.showSwingStructure || s.showSwingPoints,
    sessions: s.showSessions,
    tradeLabels: s.showTrades,
  };
}

/**
 * Apply a toolbar layer chip toggle directly onto SmcChartSettings so chips & panel stay in sync.
 */
export function applyLayerChipToggle(
  s: SmcChartSettings,
  chip: "liquidity" | "fvgOb" | "structure" | "sessions" | "tradeLabels"
): SmcChartSettings {
  const cur = deriveLayerChipStates(s);
  const next = !cur[chip];
  if (chip === "liquidity") {
    return {
      ...s,
      showEqhEql: next,
      showStrongWeakHL: next,
      showDailyHL: next,
      showWeeklyHL: next,
      showMonthlyHL: next ? s.showMonthlyHL : false,
    };
  }
  if (chip === "fvgOb") {
    return {
      ...s,
      showInternalOB: next,
      showFvg: next,
      showSwingOB: next ? s.showSwingOB : false,
    };
  }
  if (chip === "structure") {
    return {
      ...s,
      showInternalStructure: next,
      showSwingStructure: next,
      showSwingPoints: next ? s.showSwingPoints : false,
    };
  }
  if (chip === "sessions") {
    return { ...s, showSessions: next };
  }
  return { ...s, showTrades: next };
}

/**
 * Parse a CSS hex or rgba(...) string into { hex, alpha } for color-with-alpha pickers.
 */
export function parseCssColor(color: string): { hex: string; alpha: number } {
  const c = color.trim();
  const rgbaMatch = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)$/i);
  if (rgbaMatch) {
    const r = Math.min(255, Math.max(0, Number(rgbaMatch[1])));
    const g = Math.min(255, Math.max(0, Number(rgbaMatch[2])));
    const b = Math.min(255, Math.max(0, Number(rgbaMatch[3])));
    const a = rgbaMatch[4] !== undefined ? Math.min(1, Math.max(0, Number(rgbaMatch[4]))) : 1;
    const hex = `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
    return { hex, alpha: Number(a.toFixed(2)) };
  }
  if (/^#[0-9a-f]{6}$/i.test(c)) {
    return { hex: c.toLowerCase(), alpha: 1 };
  }
  return { hex: "#2157f3", alpha: 1 };
}

export function formatCssRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "").trim();
  if (clean.length !== 6) return hex;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  const a = Math.min(1, Math.max(0, alpha));
  if (a >= 0.995) return `#${clean}`;
  return `rgba(${r}, ${g}, ${b}, ${a.toFixed(2)})`;
}

/**
 * Convert an rgba color to a crisp solid/high-alpha border version (for Swing OBs).
 */
export function deriveBorderColor(fillColor: string, borderAlpha = 0.85): string {
  const { hex } = parseCssColor(fillColor);
  return formatCssRgba(hex, borderAlpha);
}
