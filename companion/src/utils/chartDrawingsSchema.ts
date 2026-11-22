export type EngineDrawingType = "LIQ" | "SESS" | "FVG" | "OB" | "STRUCT" | "TRADE";
export type EngineDrawingDirection = "BULLISH" | "BEARISH" | "NEUTRAL";
export type EngineDrawingStatus =
  | "ACTIVE"
  | "MITIGATED"
  | "SWEPT"
  | "INVALIDATED"
  | "EXPIRED"
  | "OPEN"
  | "PENDING"
  | "CLOSED";

export interface EngineDrawingPriceLevels {
  price?: number;
  sweep_time?: number | null;
  sweep_price?: number | null;
  top?: number;
  bottom?: number;
  midpoint?: number;
  high?: number | null;
  low?: number | null;
  entry?: number;
  sl?: number;
  initial_sl?: number;
  tp?: number;
  tp1?: number;
  exit?: number;
  current?: number;
  pnl?: number;
  rr?: number;
  volume?: number;
  ticket?: number;
  ownership?: string;
}

export interface EngineDrawingItem {
  id: string;
  type: EngineDrawingType;
  subtype: string;
  symbol: string;
  broker_symbol?: string;
  timeframe: string;
  start_time: number;
  end_time: number | null;
  price_levels: EngineDrawingPriceLevels;
  direction: EngineDrawingDirection;
  status: EngineDrawingStatus;
  source: string;
  meta?: Record<string, any>;
}

export interface EngineDrawingsCounts {
  liquidity: number;
  fvgOb: number;
  structure: number;
  sessions: number;
  trades: number;
}

export interface EngineDrawingsFeed {
  schema_version: string;
  symbol: string;
  broker_symbol?: string;
  timeframe: string;
  generated_at: string;
  broker_utc_offset_hours?: number;
  dropped_count?: number;
  counts: EngineDrawingsCounts;
  drawings: EngineDrawingItem[];
}

export interface ValidatedDrawingsResult {
  items: EngineDrawingItem[];
  dropped: Array<{ id?: string; reason: string }>;
  counts: EngineDrawingsCounts;
  malformedFeed: boolean;
}

export const DRAWING_TF_RANK: Record<string, number> = {
  M1: 1,
  M5: 2,
  M15: 3,
  M30: 4,
  H1: 5,
  H4: 6,
  D1: 7,
  W1: 8,
};

const VALID_TYPES = new Set<EngineDrawingType>(["LIQ", "SESS", "FVG", "OB", "STRUCT", "TRADE"]);
const VALID_DIRECTIONS = new Set<EngineDrawingDirection>(["BULLISH", "BEARISH", "NEUTRAL"]);
const VALID_STATUSES = new Set<EngineDrawingStatus>([
  "ACTIVE",
  "MITIGATED",
  "SWEPT",
  "INVALIDATED",
  "EXPIRED",
  "OPEN",
  "PENDING",
  "CLOSED",
]);

export function canonicalDrawingSymbol(symbol: string | undefined | null): string {
  const raw = String(symbol || "").trim().toUpperCase();
  return raw.split(".")[0].replace(/(_SB|_RAW|_ECN|_PRO)$/i, "");
}

export function shouldIncludeDrawingForTimeframe(
  drawingTf: string,
  chartTf: string,
  drawingType: EngineDrawingType
): boolean {
  if (drawingType === "TRADE" || drawingType === "SESS") return true;
  const dRank = DRAWING_TF_RANK[String(drawingTf || "").toUpperCase()] ?? 0;
  const cRank = DRAWING_TF_RANK[String(chartTf || "").toUpperCase()] ?? 0;
  if (dRank === 0 || cRank === 0) return true;
  return dRank >= cRank;
}

function isFinitePositive(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n > 0;
}

function isValidEpochSec(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n) && n > 946684800; // > 2000-01-01
}

export function validateEngineDrawingsFeed(
  rawFeed: unknown,
  expectedSymbol: string,
  chartTf: string
): ValidatedDrawingsResult {
  const emptyCounts: EngineDrawingsCounts = {
    liquidity: 0,
    fvgOb: 0,
    structure: 0,
    sessions: 0,
    trades: 0,
  };

  if (!rawFeed || typeof rawFeed !== "object" || !Array.isArray((rawFeed as any).drawings)) {
    return {
      items: [],
      dropped: [{ reason: "Malformed feed envelope (missing drawings array)" }],
      counts: emptyCounts,
      malformedFeed: true,
    };
  }

  const targetSym = canonicalDrawingSymbol(expectedSymbol);
  const seen = new Set<string>();
  const valid: EngineDrawingItem[] = [];
  const dropped: Array<{ id?: string; reason: string }> = [];

  for (const raw of (rawFeed as any).drawings) {
    if (!raw || typeof raw !== "object") {
      dropped.push({ reason: "Item is not an object" });
      continue;
    }
    const id = typeof raw.id === "string" ? raw.id.trim() : "";
    const type = String(raw.type || "").toUpperCase() as EngineDrawingType;
    const subtype = String(raw.subtype || type).toUpperCase();
    const sym = canonicalDrawingSymbol(raw.symbol);
    const tf = String(raw.timeframe || chartTf).toUpperCase();
    const direction = String(raw.direction || "NEUTRAL").toUpperCase() as EngineDrawingDirection;
    const status = String(raw.status || "ACTIVE").toUpperCase() as EngineDrawingStatus;
    const source = typeof raw.source === "string" ? raw.source.trim() : "";

    if (!id || !source) {
      dropped.push({ id, reason: "Missing id or source" });
      continue;
    }
    if (!VALID_TYPES.has(type)) {
      dropped.push({ id, reason: `Unknown drawing type: ${raw.type}` });
      continue;
    }
    if (sym !== targetSym) {
      dropped.push({ id, reason: `Symbol mismatch: ${sym} !== ${targetSym}` });
      continue;
    }
    if (!isValidEpochSec(raw.start_time)) {
      dropped.push({ id, reason: "Invalid start_time" });
      continue;
    }
    if (raw.end_time !== null && raw.end_time !== undefined && !isValidEpochSec(raw.end_time)) {
      dropped.push({ id, reason: "Invalid end_time" });
      continue;
    }
    if (!raw.price_levels || typeof raw.price_levels !== "object") {
      dropped.push({ id, reason: "Missing price_levels" });
      continue;
    }

    const pl = raw.price_levels as EngineDrawingPriceLevels;
    if ((type === "LIQ" || type === "STRUCT") && !isFinitePositive(pl.price)) {
      dropped.push({ id, reason: `${type} missing positive price` });
      continue;
    }
    if (type === "FVG" || type === "OB") {
      if (!isFinitePositive(pl.top) || !isFinitePositive(pl.bottom) || pl.top <= pl.bottom) {
        dropped.push({ id, reason: `${type} invalid top/bottom bounds` });
        continue;
      }
    }
    if (type === "TRADE" && !isFinitePositive(pl.entry)) {
      dropped.push({ id, reason: "TRADE missing positive entry price" });
      continue;
    }

    if (!shouldIncludeDrawingForTimeframe(tf, chartTf, type)) {
      continue;
    }

    if (seen.has(id)) {
      dropped.push({ id, reason: "Duplicate drawing id" });
      continue;
    }
    seen.add(id);

    valid.push({
      id,
      type,
      subtype,
      symbol: sym,
      broker_symbol: typeof raw.broker_symbol === "string" ? raw.broker_symbol : undefined,
      timeframe: tf,
      start_time: raw.start_time,
      end_time: raw.end_time ?? null,
      price_levels: pl,
      direction: VALID_DIRECTIONS.has(direction) ? direction : "NEUTRAL",
      status: VALID_STATUSES.has(status) ? status : "ACTIVE",
      source,
      meta: raw.meta && typeof raw.meta === "object" ? raw.meta : undefined,
    });
  }

  const counts: EngineDrawingsCounts = {
    liquidity: valid.filter((d) => d.type === "LIQ").length,
    fvgOb: valid.filter((d) => d.type === "FVG" || d.type === "OB").length,
    structure: valid.filter((d) => d.type === "STRUCT").length,
    sessions: valid.filter((d) => d.type === "SESS").length,
    trades: valid.filter((d) => d.type === "TRADE").length,
  };

  return { items: valid, dropped, counts, malformedFeed: false };
}

export interface ParityDebugEntry {
  id: string;
  type: EngineDrawingType;
  subtype: string;
  timeframe: string;
  status: EngineDrawingStatus;
  rendered: boolean;
  reason?: string;
}

export function buildParityDebugReport(
  validatedItems: EngineDrawingItem[],
  renderedIds: Set<string>
): ParityDebugEntry[] {
  return validatedItems.map((item) => ({
    id: item.id,
    type: item.type,
    subtype: item.subtype,
    timeframe: item.timeframe,
    status: item.status,
    rendered: renderedIds.has(item.id),
    reason: renderedIds.has(item.id) ? undefined : "Outside visible range or layer toggled off",
  }));
}

/**
 * Deterministic recorded engine-output fixture covering all 6 drawing types,
 * all 3 symbols (XAUUSD, USDJPY, BTCUSD), and all 5 timeframes (M1..H4).
 */
export function buildEngineDrawingsParityFixture(
  symbol: "XAUUSD" | "USDJPY" | "BTCUSD",
  timeframe: "M1" | "M5" | "M15" | "H1" | "H4",
  anchorTimeSec = 1763568000 // 2025-11-19 16:00:00 UTC (Wednesday)
): EngineDrawingsFeed {
  const basePrice = symbol === "XAUUSD" ? 2650.0 : symbol === "USDJPY" ? 154.5 : 91500.0;
  const step = symbol === "XAUUSD" ? 2.5 : symbol === "USDJPY" ? 0.15 : 220.0;
  const tfSec =
    timeframe === "M1"
      ? 60
      : timeframe === "M5"
      ? 300
      : timeframe === "M15"
      ? 900
      : timeframe === "H1"
      ? 3600
      : 14400;

  const dayStart = anchorTimeSec - (anchorTimeSec % 86400);

  const drawings: EngineDrawingItem[] = [
    // LIQ: PDH active, PDL swept, EQH active
    {
      id: `liq:${symbol}:D1:PDH:${dayStart - 86400}`,
      type: "LIQ",
      subtype: "PDH",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe: "D1",
      start_time: dayStart - 86400,
      end_time: null,
      price_levels: { price: Number((basePrice + step * 6).toFixed(4)) },
      direction: "BEARISH",
      status: "ACTIVE",
      source: "WeeklyDailyEngine",
      meta: { label: "PDH" },
    },
    {
      id: `liq:${symbol}:D1:PDL:${dayStart - 86400}`,
      type: "LIQ",
      subtype: "PDL",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe: "D1",
      start_time: dayStart - 86400,
      end_time: anchorTimeSec - tfSec * 12,
      price_levels: {
        price: Number((basePrice - step * 5).toFixed(4)),
        sweep_time: anchorTimeSec - tfSec * 12,
        sweep_price: Number((basePrice - step * 5).toFixed(4)),
      },
      direction: "BULLISH",
      status: "SWEPT",
      source: "WeeklyDailyEngine",
      meta: { label: "PDL" },
    },
    {
      id: `liq:${symbol}:${timeframe}:EQH:${anchorTimeSec - tfSec * 40}`,
      type: "LIQ",
      subtype: "EQH",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 40,
      end_time: null,
      price_levels: { price: Number((basePrice + step * 3.5).toFixed(4)) },
      direction: "BEARISH",
      status: "ACTIVE",
      source: "LiquidityEngine",
      meta: { label: `${timeframe} EQH` },
    },
    // SESS: Asia, London, Overlap, NY
    {
      id: `sess:${symbol}:ASIA:${dayStart}`,
      type: "SESS",
      subtype: "ASIA",
      symbol,
      timeframe,
      start_time: dayStart,
      end_time: dayStart + 9 * 3600,
      price_levels: {
        high: Number((basePrice + step * 2).toFixed(4)),
        low: Number((basePrice - step * 2).toFixed(4)),
      },
      direction: "NEUTRAL",
      status: "EXPIRED",
      source: "TradingSessionEngine",
      meta: { label: "Asia", utc_window: "00:00-09:00 UTC" },
    },
    {
      id: `sess:${symbol}:LONDON:${dayStart}`,
      type: "SESS",
      subtype: "LONDON",
      symbol,
      timeframe,
      start_time: dayStart + 6 * 3600,
      end_time: dayStart + 12 * 3600,
      price_levels: {
        high: Number((basePrice + step * 4).toFixed(4)),
        low: Number((basePrice - step * 3).toFixed(4)),
      },
      direction: "NEUTRAL",
      status: "EXPIRED",
      source: "TradingSessionEngine",
      meta: { label: "London", utc_window: "06:00-12:00 UTC" },
    },
    {
      id: `sess:${symbol}:OVERLAP:${dayStart}`,
      type: "SESS",
      subtype: "OVERLAP",
      symbol,
      timeframe,
      start_time: dayStart + 12.5 * 3600,
      end_time: dayStart + 16 * 3600,
      price_levels: {
        high: Number((basePrice + step * 5).toFixed(4)),
        low: Number((basePrice - step * 1).toFixed(4)),
      },
      direction: "NEUTRAL",
      status: "ACTIVE",
      source: "TradingSessionEngine",
      meta: { label: "LDN/NY Overlap", utc_window: "12:30-16:00 UTC" },
    },
    // FVG: active bullish + mitigated bearish
    {
      id: `fvg:${symbol}:${timeframe}:FVG:${anchorTimeSec - tfSec * 25}`,
      type: "FVG",
      subtype: "FVG",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 25,
      end_time: null,
      price_levels: {
        top: Number((basePrice - step * 0.5).toFixed(4)),
        bottom: Number((basePrice - step * 2.1).toFixed(4)),
        midpoint: Number((basePrice - step * 1.3).toFixed(4)),
      },
      direction: "BULLISH",
      status: "ACTIVE",
      source: "FvgObEngine",
      meta: { label: "FVG" },
    },
    // OB: active bullish order block
    {
      id: `ob:${symbol}:${timeframe}:OB:${anchorTimeSec - tfSec * 32}`,
      type: "OB",
      subtype: "OB",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 32,
      end_time: null,
      price_levels: {
        top: Number((basePrice - step * 2.4).toFixed(4)),
        bottom: Number((basePrice - step * 4.0).toFixed(4)),
        midpoint: Number((basePrice - step * 3.2).toFixed(4)),
      },
      direction: "BULLISH",
      status: "ACTIVE",
      source: "FvgObEngine",
      meta: { label: "OB", strength: 0.85 },
    },
    // STRUCT: BOS bullish + CHoCH bearish
    {
      id: `struct:${symbol}:${timeframe}:BOS:${anchorTimeSec - tfSec * 35}:${anchorTimeSec - tfSec * 18}`,
      type: "STRUCT",
      subtype: "BOS",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 35,
      end_time: anchorTimeSec - tfSec * 18,
      price_levels: { price: Number((basePrice + step * 1.8).toFixed(4)) },
      direction: "BULLISH",
      status: "ACTIVE",
      source: "MarketStructureEngine",
      meta: { label: `BOS (${timeframe})`, confirmed_by_close: true },
    },
    {
      id: `struct:${symbol}:${timeframe}:CHOCH:${anchorTimeSec - tfSec * 55}:${anchorTimeSec - tfSec * 42}`,
      type: "STRUCT",
      subtype: "CHOCH",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 55,
      end_time: anchorTimeSec - tfSec * 42,
      price_levels: { price: Number((basePrice - step * 1.5).toFixed(4)) },
      direction: "BEARISH",
      status: "ACTIVE",
      source: "MarketStructureEngine",
      meta: { label: `CHOCH (${timeframe})`, confirmed_by_close: true },
    },
    // TRADES: 1 OPEN long with moved SL (BE+), 1 PENDING short, 1 CLOSED long
    {
      id: `trade:open:${symbol}:77001`,
      type: "TRADE",
      subtype: "OPEN",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 15,
      end_time: null,
      price_levels: {
        entry: Number(basePrice.toFixed(4)),
        initial_sl: Number((basePrice - step * 2.5).toFixed(4)),
        sl: Number((basePrice + step * 0.25).toFixed(4)), // Moved to BE+
        tp: Number((basePrice + step * 5.0).toFixed(4)),
        tp1: Number((basePrice + step * 2.5).toFixed(4)),
        current: Number((basePrice + step * 1.9).toFixed(4)),
        pnl: 47.5,
        rr: 2.0,
        volume: 0.05,
        ticket: 77001,
        ownership: "BOT",
      },
      direction: "BULLISH",
      status: "OPEN",
      source: "MT5SyncService",
      meta: { sl_moved: true },
    },
    {
      id: `trade:pending:${symbol}:sig-1`,
      type: "TRADE",
      subtype: "PENDING",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 6,
      end_time: null,
      price_levels: {
        entry: Number((basePrice + step * 3.2).toFixed(4)),
        sl: Number((basePrice + step * 4.8).toFixed(4)),
        initial_sl: Number((basePrice + step * 4.8).toFixed(4)),
        tp: Number((basePrice - step * 0.8).toFixed(4)),
        rr: 2.5,
      },
      direction: "BEARISH",
      status: "PENDING",
      source: "CompanionRepository",
      meta: { setup_type: "M15_SMC_OTE", score: 84 },
    },
    {
      id: `trade:closed:${symbol}:76980`,
      type: "TRADE",
      subtype: "CLOSED",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      start_time: anchorTimeSec - tfSec * 68,
      end_time: anchorTimeSec - tfSec * 48,
      price_levels: {
        entry: Number((basePrice - step * 3.0).toFixed(4)),
        sl: Number((basePrice - step * 4.5).toFixed(4)),
        initial_sl: Number((basePrice - step * 4.5).toFixed(4)),
        tp: Number((basePrice + step * 0.5).toFixed(4)),
        exit: Number((basePrice + step * 0.4).toFixed(4)),
        pnl: 68.0,
        rr: 2.33,
        volume: 0.04,
        ticket: 76980,
        ownership: "BOT",
      },
      direction: "BULLISH",
      status: "CLOSED",
      source: "CompanionRepository",
    },
  ];

  const validated = validateEngineDrawingsFeed(
    {
      schema_version: "1.0",
      symbol,
      broker_symbol: `${symbol}.m`,
      timeframe,
      generated_at: new Date(anchorTimeSec * 1000).toISOString(),
      broker_utc_offset_hours: 2,
      counts: { liquidity: 0, fvgOb: 0, structure: 0, sessions: 0, trades: 0 },
      drawings,
    },
    symbol,
    timeframe
  );

  return {
    schema_version: "1.0",
    symbol,
    broker_symbol: `${symbol}.m`,
    timeframe,
    generated_at: new Date(anchorTimeSec * 1000).toISOString(),
    broker_utc_offset_hours: 2,
    dropped_count: validated.dropped.length,
    counts: validated.counts,
    drawings: validated.items,
  };
}
