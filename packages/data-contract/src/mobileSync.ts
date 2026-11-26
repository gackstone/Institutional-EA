import { z } from "zod";

export const MOBILE_SYNC_SCHEMA_VERSION = "1.0.0" as const;

export const ALLOWED_MOBILE_HTTP_METHODS = ["GET"] as const;
export const ALLOWED_MOBILE_AUTH_ENDPOINTS = [
  "/api/mobile/v1/pair",
  "/api/mobile/v1/unpair",
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

export const MobileTradesPageSchema = z.object({
  page: z.number().int().positive(),
  limit: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  hasMore: z.boolean(),
  currency: z.string().min(1).max(12),
  summary: z.object({
    count: z.number().int().nonnegative(),
    netPnl: z.number().finite(),
    winRate: z.number().min(0).max(100),
    wins: z.number().int().nonnegative(),
    losses: z.number().int().nonnegative(),
  }),
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
  start_time: z.number().int(),
  end_time: z.number().int().nullable(),
  price_levels: z.record(z.string(), z.any()),
  status: z.string(),
  source: z.string(),
  meta: z.record(z.string(), z.any()).optional(),
});
export type MobileDrawingItem = z.infer<typeof MobileDrawingItemSchema>;

export const MobileDrawingsResponseSchema = z.object({
  schema_version: z.string().default("1.0"),
  symbol: z.string(),
  broker_symbol: z.string().optional(),
  timeframe: z.string(),
  generated_at: z.string().optional(),
  source: z.string().default("BOT"),
  items: z.array(MobileDrawingItemSchema),
  counts: z.record(z.string(), z.number()).optional(),
  mtf_levels: z.array(z.any()).optional(),
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
 * Validates that a mobile HTTP request is strictly read-only.
 * Only GET is permitted for data endpoints; POST is permitted exclusively
 * for /api/mobile/v1/pair and /api/mobile/v1/unpair.
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
