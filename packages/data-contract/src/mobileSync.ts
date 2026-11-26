import { z } from "zod";

export const MOBILE_SYNC_SCHEMA_VERSION = "1.1.0" as const;
export const SUPPORTED_MOBILE_SYNC_SCHEMA_VERSIONS = ["1.0.0", "1.1.0"] as const;

export const ALLOWED_MOBILE_HTTP_METHODS = ["GET"] as const;
export const ALLOWED_MOBILE_AUTH_ENDPOINTS = [
  "/api/mobile/v1/pair",
  "/api/mobile/v1/unpair",
  "/functions/v1/mobile-pairing",
] as const;

export const MobileBotStateSchema = z.enum([
  "RUNNING",
  "PAUSED",
  "STOPPED",
  "STARTING",
  "ERROR",
  "EMERGENCY_STOP",
  "UNKNOWN",
]);
export type MobileBotState = z.infer<typeof MobileBotStateSchema>;

export const MobileMt5StatusSchema = z.enum([
  "CONNECTED",
  "DISCONNECTED",
  "SYNCHRONIZING",
  "ERROR",
]);
export type MobileMt5Status = z.infer<typeof MobileMt5StatusSchema>;

export const MobileSyncMetaSchema = z.object({
  schemaVersion: z.string().min(1).default(MOBILE_SYNC_SCHEMA_VERSION),
  minClientSchemaVersion: z.string().default("1.0.0"),
  supportedVersions: z.array(z.string()).default(["1.0.0", "1.1.0"]),
  producerVersion: z.string().min(1).default("1.3.7"),
  generatedAt: z.string(),
  sequenceNo: z.number().int().nonnegative().default(0),
  timezoneRule: z.string().default("UTC_00_00"),
  brokerUtcOffsetHours: z.number().int().default(0),
});
export type MobileSyncMeta = z.infer<typeof MobileSyncMetaSchema>;

export const MobileStatusSchema = z.object({
  schemaVersion: z.string().min(1),
  appVersion: z.string().min(1),
  botState: MobileBotStateSchema,
  mt5Connected: z.boolean(),
  mt5Status: MobileMt5StatusSchema,
  demoMode: z.boolean(),
  broker: z.string(),
  accountMasked: z.string(),
  lastHeartbeat: z.string().nullable(),
  serverTime: z.string(),
  readOnlyEnforced: z.literal(true),
});
export type MobileStatus = z.infer<typeof MobileStatusSchema>;

export const MobileAccountSchema = z.object({
  balance: z.number().finite(),
  equity: z.number().finite(),
  margin: z.number().finite(),
  freeMargin: z.number().finite(),
  marginLevel: z.number().finite(),
  floatingPnl: z.number().finite(),
  currency: z.string().min(1).max(12),
  leverage: z.number().int().nonnegative(),
  tradeMode: z.string(),
  broker: z.string(),
  accountMasked: z.string(),
  openPositionsCount: z.number().int().nonnegative(),
  updatedAt: z.string().nullable(),
});
export type MobileAccount = z.infer<typeof MobileAccountSchema>;

export const MobileStatsSchema = z.object({
  todayPnl: z.number().finite(),
  todayRealizedPnl: z.number().finite().optional(),
  todayClosedCount: z.number().int().nonnegative().optional(),
  openPositionsCount: z.number().int().nonnegative().optional(),
  totalProfit: z.number().finite(),
  winRate: z.number().min(0).max(100),
  dealsCount: z.number().int().nonnegative(),
  tradesToday: z.number().int().nonnegative(),
  winsCount: z.number().int().nonnegative(),
  lossesCount: z.number().int().nonnegative(),
  currency: z.string().min(1).max(12),
  computedAt: z.string(),
});
export type MobileStats = z.infer<typeof MobileStatsSchema>;

export const MobilePositionSchema = z.object({
  ticket: z.number().int().positive(),
  symbol: z.string().min(1),
  canonicalSymbol: z.string().min(1),
  type: z.enum(["BUY", "SELL"]),
  volume: z.number().positive(),
  openPrice: z.number().finite(),
  currentPrice: z.number().finite(),
  sl: z.number().finite().nullable(),
  tp: z.number().finite().nullable(),
  profit: z.number().finite(),
  swap: z.number().finite().default(0),
  openTime: z.number().int().nonnegative(),
  digits: z.number().int().min(0).max(8).default(2),
  ownership: z.enum(["BOT_OWN", "MANUAL", "OTHER_EA"]).default("BOT_OWN"),
  protected: z.boolean().optional(),
  comment: z.string().default(""),
});
export type MobilePosition = z.infer<typeof MobilePositionSchema>;

export const MobilePositionsResponseSchema = z.object({
  positions: z.array(MobilePositionSchema),
  currency: z.string().min(1).max(12),
  updatedAt: z.string().nullable(),
});
export type MobilePositionsResponse = z.infer<typeof MobilePositionsResponseSchema>;

export const MobileTradeRecordSchema = z.object({
  ticket: z.number().int(),
  symbol: z.string().min(1),
  canonicalSymbol: z.string().min(1),
  direction: z.enum(["BUY", "SELL"]),
  volume: z.number().nonnegative(),
  entryPrice: z.number().finite().nullable(),
  exitPrice: z.number().finite().nullable(),
  sl: z.number().finite().nullable(),
  tp: z.number().finite().nullable(),
  pnl: z.number().finite(),
  openedAt: z.string().nullable(),
  closedAt: z.string().nullable(),
  durationSec: z.number().nonnegative().nullable(),
  status: z.string(),
  strategyTag: z.string().default(""),
  digits: z.number().int().min(0).max(8).default(2),
});
export type MobileTradeRecord = z.infer<typeof MobileTradeRecordSchema>;

export const MobileTradesSummarySchema = z.object({
  count: z.number().int().nonnegative(),
  netPnl: z.number().finite(),
  winRate: z.number().min(0).max(100),
  wins: z.number().int().nonnegative(),
  losses: z.number().int().nonnegative(),
});
export type MobileTradesSummary = z.infer<typeof MobileTradesSummarySchema>;

export const MobileTradesPageSchema = z.object({
  page: z.number().int().positive(),
  limit: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  hasMore: z.boolean(),
  nextCursor: z.string().nullable().optional().default(null),
  currency: z.string().min(1).max(12),
  summary: MobileTradesSummarySchema,
  items: z.array(MobileTradeRecordSchema),
});
export type MobileTradesPage = z.infer<typeof MobileTradesPageSchema>;

export const MobileCandleSchema = z.object({
  time: z.number().int().positive(),
  open: z.number().finite(),
  high: z.number().finite(),
  low: z.number().finite(),
  close: z.number().finite(),
  volume: z.number().nonnegative().default(0),
});
export type MobileCandle = z.infer<typeof MobileCandleSchema>;

export const MobileCandlesResponseSchema = z.object({
  symbol: z.string().min(1),
  brokerSymbol: z.string().min(1),
  timeframe: z.string().min(1),
  digits: z.number().int().min(0).max(8),
  point: z.number().positive(),
  bid: z.number().finite().nullable(),
  ask: z.number().finite().nullable(),
  spreadPoints: z.number().finite().nullable(),
  candles: z.array(MobileCandleSchema),
  stale: z.boolean().default(false),
  marketClosed: z.boolean().default(false),
  tickTimeUtc: z.string().nullable().default(null),
  source: z.string().default("MT5"),
});
export type MobileCandlesResponse = z.infer<typeof MobileCandlesResponseSchema>;

export const MobileDrawingItemSchema = z.object({
  id: z.string().min(1),
  type: z.enum(["LIQ", "SESS", "FVG", "OB", "STRUCT", "TRADE"]),
  subtype: z.string(),
  direction: z.enum(["BULLISH", "BEARISH", "NEUTRAL"]),
  timeframe: z.string(),
  symbol: z.string(),
  broker_symbol: z.string().optional(),
  start_time: z.number().int(),
  end_time: z.number().int().nullable(),
  price_levels: z.record(z.string(), z.any()),
  status: z.string(),
  source: z.string(),
  meta: z.record(z.string(), z.any()).optional(),
});
export type MobileDrawingItem = z.infer<typeof MobileDrawingItemSchema>;

export const MobileDrawingsResponseSchema = z.object({
  schema_version: z.string().default("1.1.0"),
  symbol: z.string(),
  broker_symbol: z.string().optional(),
  timeframe: z.string(),
  generated_at: z.string().optional(),
  source: z.string().default("BOT"),
  items: z.array(MobileDrawingItemSchema),
  drawings: z.array(MobileDrawingItemSchema).optional(),
  counts: z.record(z.string(), z.number()).optional(),
  mtf_levels: z.array(z.any()).optional(),
  smc: z.record(z.string(), z.any()).optional(),
});
export type MobileDrawingsResponse = z.infer<typeof MobileDrawingsResponseSchema>;

export const MobileSymbolSpecSchema = z.object({
  symbol: z.string().min(1),
  brokerSymbol: z.string().min(1),
  digits: z.number().int().min(0).max(8),
  point: z.number().positive(),
  bid: z.number().finite().nullable(),
  ask: z.number().finite().nullable(),
  spreadPoints: z.number().finite().nullable(),
});
export type MobileSymbolSpec = z.infer<typeof MobileSymbolSpecSchema>;

export const MobileSymbolsResponseSchema = z.object({
  symbols: z.array(MobileSymbolSpecSchema),
  timeframes: z.array(z.string().min(1)),
  layers: z.array(z.string().min(1)),
});
export type MobileSymbolsResponse = z.infer<typeof MobileSymbolsResponseSchema>;

export const MobileEquityPointSchema = z.object({
  time: z.number().int().nonnegative(),
  balance: z.number().finite(),
  equity: z.number().finite(),
  pnl: z.number().finite(),
});
export type MobileEquityPoint = z.infer<typeof MobileEquityPointSchema>;

export const MobileEquityResponseSchema = z.object({
  range: z.enum(["1D", "1W", "1M", "ALL"]),
  currency: z.string().min(1).max(12),
  points: z.array(MobileEquityPointSchema),
});
export type MobileEquityResponse = z.infer<typeof MobileEquityResponseSchema>;

export const MobileActivityEventSchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  type: z.string(),
  severity: z.string(),
  symbol: z.string().nullable(),
  message: z.string(),
  ticket: z.number().int().nullable().default(null),
});
export type MobileActivityEvent = z.infer<typeof MobileActivityEventSchema>;

export const MobileActivityResponseSchema = z.object({
  events: z.array(MobileActivityEventSchema),
});
export type MobileActivityResponse = z.infer<typeof MobileActivityResponseSchema>;

export const MobileLiveSignalStatusSchema = z.enum([
  "New",
  "Active",
  "Triggered",
  "Expired",
  "Invalidated",
]);
export type MobileLiveSignalStatus = z.infer<typeof MobileLiveSignalStatusSchema>;

export const MobileLiveSignalSchema = z.object({
  id: z.string().min(1),
  symbol: z.string().min(1),
  direction: z.enum(["BUY", "SELL"]),
  timeframe: z.string().default("M15"),
  entryPrice: z.number().finite().nullable(),
  stopLoss: z.number().finite().nullable(),
  takeProfit: z.number().finite().nullable(),
  rr: z.number().finite().nullable(),
  strategy: z.string().default(""),
  score: z.number().finite().nullable().default(null),
  status: MobileLiveSignalStatusSchema,
  analysis: z.string().default(""),
  createdAt: z.string(),
  expiresAt: z.string().nullable().default(null),
});
export type MobileLiveSignal = z.infer<typeof MobileLiveSignalSchema>;

export const MobileLiveSignalsResponseSchema = z.object({
  signals: z.array(MobileLiveSignalSchema),
  updatedAt: z.string().nullable(),
});
export type MobileLiveSignalsResponse = z.infer<typeof MobileLiveSignalsResponseSchema>;

export const MobilePairingQrPayloadSchema = z.object({
  v: z.literal(1),
  host: z.string().min(1),
  hosts: z.array(z.string().min(1)).optional(),
  port: z.number().int().min(1024).max(65535),
  code: z.string().regex(/^[0-9]{6}$/, "Pairing code must be 6 digits"),
  expiresAt: z.number().int().positive(),
  companionName: z.string().optional(),
});
export type MobilePairingQrPayload = z.infer<typeof MobilePairingQrPayloadSchema>;

export const CloudPairingQrPayloadSchema = z.object({
  v: z.literal(2),
  mode: z.literal("cloud"),
  cloudUrl: z.string().url(),
  sessionId: z.string().min(8),
  sessionToken: z.string().min(16),
  code: z.string().regex(/^[0-9]{6}$/, "Pairing code must be 6 digits"),
  expiresAt: z.number().int().positive(),
  companionName: z.string().optional(),
});
export type CloudPairingQrPayload = z.infer<typeof CloudPairingQrPayloadSchema>;

export const AnyPairingQrPayloadSchema = z.union([
  CloudPairingQrPayloadSchema,
  MobilePairingQrPayloadSchema,
]);
export type AnyPairingQrPayload = z.infer<typeof AnyPairingQrPayloadSchema>;

export const MobilePairResponseSchema = z.object({
  deviceId: z.string().min(1),
  deviceToken: z.string().min(16),
  companionName: z.string().min(1),
  schemaVersion: z.string().min(1),
  readOnly: z.literal(true),
  pairedAt: z.string(),
});
export type MobilePairResponse = z.infer<typeof MobilePairResponseSchema>;

export const MobileSseEventSchema = z.object({
  type: z.enum([
    "snapshot",
    "tick",
    "candle",
    "positions",
    "status",
    "activity",
    "drawings",
    "ping",
    "revoked",
  ]),
  timestamp: z.string(),
  payload: z.unknown(),
});
export type MobileSseEvent = z.infer<typeof MobileSseEventSchema>;

/**
 * Negotiates schema version compatibility between Producer and Consumer.
 * - Both 1.0.0 and 1.1.0 are supported (v1.1.0 is additive and backward-compatible with v1.0.0).
 * - If major version differs (e.g. "2.0.0"), returns `compatible: false` with `updateNeeded: true`.
 */
export function checkSyncSchemaCompatibility(
  producerSchemaVersion: string | null | undefined,
  clientSchemaVersion: string = MOBILE_SYNC_SCHEMA_VERSION
): {
  compatible: boolean;
  updateNeeded: boolean;
  producerVersion: string;
  clientVersion: string;
  reason: string;
} {
  const prod = String(producerSchemaVersion || "1.0.0").trim();
  const cli = String(clientSchemaVersion || MOBILE_SYNC_SCHEMA_VERSION).trim();
  const prodMajor = Number(prod.split(".")[0] || 1);
  const cliMajor = Number(cli.split(".")[0] || 1);
  if (prodMajor !== cliMajor) {
    return {
      compatible: false,
      updateNeeded: true,
      producerVersion: prod,
      clientVersion: cli,
      reason:
        prodMajor > cliMajor
          ? `Android app update required (Companion is on Sync Schema v${prod}, app supports v${cli}).`
          : `Windows Companion update required (App is on Sync Schema v${cli}, Companion is on v${prod}).`,
    };
  }
  return {
    compatible: true,
    updateNeeded: false,
    producerVersion: prod,
    clientVersion: cli,
    reason: "Compatible",
  };
}

/**
 * Normalizes drawings counts so both camelCase (`liquidity`, `fvgOb`, `structure`, `sessions`, `trades`)
 * and uppercase layer keys (`LIQ`, `FVG`, `OB`, `FVG_OB`, `STRUCT`, `SESS`, `TRADE`, `TRADES`) are present.
 */
export function normalizeDrawingsCounts(
  items: Array<{ type?: string }>,
  rawCounts?: Record<string, number> | null
): Record<string, number> {
  const liq = items.filter((d) => d.type === "LIQ").length;
  const fvg = items.filter((d) => d.type === "FVG").length;
  const ob = items.filter((d) => d.type === "OB").length;
  const fvgOb = fvg + ob;
  const struct = items.filter((d) => d.type === "STRUCT").length;
  const sess = items.filter((d) => d.type === "SESS").length;
  const trade = items.filter((d) => d.type === "TRADE").length;

  const hasItems = items.length > 0;
  return {
    liquidity: hasItems ? liq : Number(rawCounts?.liquidity ?? rawCounts?.LIQ ?? 0),
    fvgOb: hasItems ? fvgOb : Number(rawCounts?.fvgOb ?? rawCounts?.FVG_OB ?? ((rawCounts?.FVG ?? 0) + (rawCounts?.OB ?? 0))),
    structure: hasItems ? struct : Number(rawCounts?.structure ?? rawCounts?.STRUCT ?? 0),
    sessions: hasItems ? sess : Number(rawCounts?.sessions ?? rawCounts?.SESS ?? 0),
    trades: hasItems ? trade : Number(rawCounts?.trades ?? rawCounts?.TRADE ?? rawCounts?.TRADES ?? 0),
    LIQ: hasItems ? liq : Number(rawCounts?.LIQ ?? rawCounts?.liquidity ?? 0),
    FVG: hasItems ? fvg : Number(rawCounts?.FVG ?? 0),
    OB: hasItems ? ob : Number(rawCounts?.OB ?? 0),
    FVG_OB: hasItems ? fvgOb : Number(rawCounts?.FVG_OB ?? rawCounts?.fvgOb ?? 0),
    STRUCT: hasItems ? struct : Number(rawCounts?.STRUCT ?? rawCounts?.structure ?? 0),
    SESS: hasItems ? sess : Number(rawCounts?.SESS ?? rawCounts?.sessions ?? 0),
    TRADE: hasItems ? trade : Number(rawCounts?.TRADE ?? rawCounts?.trades ?? 0),
    TRADES: hasItems ? trade : Number(rawCounts?.TRADES ?? rawCounts?.trades ?? 0),
  };
}

/**
 * Validates that a mobile HTTP request is strictly read-only.
 * Only GET is permitted for data endpoints; POST is permitted exclusively
 * for /api/mobile/v1/pair, /api/mobile/v1/unpair, and /functions/v1/mobile-pairing.
 */
export function assertMobileHttpReadOnly(method: string, path: string): void {
  const normalizedMethod = method.trim().toUpperCase();
  const cleanPath = path.split("?")[0];
  if (normalizedMethod === "GET") {
    return;
  }
  if (
    normalizedMethod === "POST" &&
    (ALLOWED_MOBILE_AUTH_ENDPOINTS as readonly string[]).includes(cleanPath)
  ) {
    return;
  }
  throw new Error(
    `READ_ONLY_ENFORCED: Mobile client cannot invoke ${normalizedMethod} ${cleanPath}`
  );
}
